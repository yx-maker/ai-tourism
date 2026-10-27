"""高德 POI 门票价格补库脚本（运维工具，非运行时组件）。

用途：
    批量回填 t_poi.ticket_price 为空的景点，数据源为高德 POI 文本搜索
    （extensions=all 的 biz_ext.cost 字段）。

重要结论（2026-10-23 实测 + 官方文档核实）：
    高德 Web 服务 API **不提供景点门票价格数据**：
    - biz_ext.cost 的官方语义是「人均消费」，仅存在于餐饮/酒店/景点/影院类 POI，
      且景点类几乎不返回值（实测故宫/迪士尼/环球度假区 cost 均为空数组 []，
      餐饮如海底捞返回 120.00 是人均消费，与门票无关）；
    - ticket_ordering（是否可订票）字段官方标注「逐渐废弃」，实测恒为 "0"。
    因此本脚本在当前高德 Key 下预期 0 填充。保留它的价值：
    Key 升级/更换数据源后可作为兜底通道；更重要的是它固化了
    「查不到留空、绝不编造」的正确行为。景点门票的真实路径是
    t_poi 已有价格 → POI 库城市均价 → 预算引擎系数估算（界面标注来源）。

设计原则（与预算引擎的数据真实性分层一致）：
    1. 只写入真实查到的价格；查不到一律留空，绝不编造默认值。
    2. 免费景点（cost 明确为 0）也视为真实数据，写入 0。
    3. 默认 --dry-run 只打印将要写入的内容，确认无误后加 --apply 才落库。
    4. 单条失败不影响整体，末尾输出统计报告。

用法：
    # 预演（默认，不写库）
    python script/backfill_ticket_price.py

    # 实际写入
    python script/backfill_ticket_price.py --apply

    # 只补某个城市
    python script/backfill_ticket_price.py --apply --city 杭州

依赖：pymysql（pip install pymysql）
高德 Key：读取环境变量 AMAP_WEB_API_KEY，或命令行 --amap-key 传入。
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional, Tuple

AMAP_PLACE_TEXT_URL = "https://restapi.amap.com/v3/place/text"
REQUEST_INTERVAL_SECONDS = 0.25  # 高德免费 Key QPS 限制保守值

# 与 application.yml 的 datasource 对齐（可通过环境变量或参数覆盖）
DEFAULT_DB = dict(
    host=os.getenv("DB_HOST", "127.0.0.1"),
    port=int(os.getenv("DB_PORT", "3306")),
    user=os.getenv("DB_USER", "root"),
    password=os.getenv("DB_PASSWORD", "123456"),
    database=os.getenv("DB_NAME", "aitourism"),
)


@dataclass
class PoiRow:
    id: int
    poi_name: str
    city_name: str


@dataclass
class BackfillResult:
    poi: PoiRow
    price: Optional[Decimal]  # None=未查到
    amap_name: str = ""       # 高德返回的 POI 名（核对匹配度用）
    note: str = ""            # 失败原因 / 匹配说明


@dataclass
class Stats:
    total: int = 0
    filled: int = 0
    free: int = 0
    not_found: int = 0
    no_cost_data: int = 0
    api_error: int = 0
    skipped_exists: int = 0
    details: List[BackfillResult] = field(default_factory=list)


def http_get_json(url: str, timeout: int = 10) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json_loads(resp.read().decode("utf-8"))


def json_loads(text: str) -> dict:
    import json

    return json.loads(text)


def parse_cost(raw) -> Optional[Decimal]:
    """解析 biz_ext.cost。

    高德返回形态不固定，可能是：
      - []：无数据
      - ["60"]：字符串金额
      - [{"price": "60"}]：对象
      - ["免费"] / ["0"]：免费
    解析不了返回 None（不猜）。
    """
    if raw is None:
        return None
    if isinstance(raw, (str, int, float)):
        items = [raw]
    elif isinstance(raw, list):
        items = raw
    else:
        return None

    for item in items:
        text = ""
        if isinstance(item, dict):
            text = str(item.get("cost") or item.get("price") or "").strip()
        else:
            text = str(item).strip()
        if not text:
            continue
        if text in ("免费", "免费开放", "0", "0.0", "0元"):
            return Decimal("0")
        m = re.search(r"(\d+(?:\.\d+)?)", text)
        if m:
            try:
                value = Decimal(m.group(1))
            except InvalidOperation:
                continue
            # 合理票价区间过滤（0-2000 元），避免误抓「演出场次 360」等噪音
            if Decimal("0") <= value <= Decimal("2000"):
                return value
    return None


def query_amap_ticket(keyword: str, city: str, amap_key: str) -> Tuple[Optional[Decimal], str, str]:
    """返回 (price, amap_poi_name, note)。price=None 表示未查到真实价格。"""
    params = {
        "key": amap_key,
        "keywords": keyword,
        "city": city,
        "extensions": "all",
        "output": "JSON",
        "offset": 5,  # 多取几个候选，便于挑选名称最匹配的
    }
    url = AMAP_PLACE_TEXT_URL + "?" + urllib.parse.urlencode(params)
    try:
        data = http_get_json(url)
    except Exception as e:  # noqa: BLE001
        return None, "", f"API请求失败: {e}"

    if str(data.get("status")) != "1":
        return None, "", f"API返回异常: status={data.get('status')} info={data.get('info')}"

    pois = data.get("pois") or []
    if not pois:
        return None, "", "高德无此POI"

    # 优先取名称包含关键词的第一个候选，否则取第一个
    best = None
    for p in pois:
        name = p.get("name") or ""
        if keyword in name or name in keyword:
            best = p
            break
    if best is None:
        best = pois[0]

    amap_name = best.get("name") or ""
    biz_ext = best.get("biz_ext") or {}
    if not isinstance(biz_ext, dict):
        return None, amap_name, "biz_ext结构异常"

    price = parse_cost(biz_ext.get("cost"))
    if price is None:
        return None, amap_name, "高德未提供票价(cost为空)"
    return price, amap_name, ""


def load_pois_to_fill(conn, city: Optional[str]) -> List[PoiRow]:
    sql = (
        "SELECT id, poi_name, city_name FROM t_poi "
        "WHERE ticket_price IS NULL OR ticket_price = 0"
    )
    args: list = []
    if city:
        sql += " AND city_name = %s"
        args.append(city)
    sql += " ORDER BY city_name, poi_rankInCity"
    with conn.cursor() as cur:
        cur.execute(sql, args)
        return [PoiRow(id=r[0], poi_name=r[1], city_name=r[2]) for r in cur.fetchall()]


def count_missing(conn, city: Optional[str]) -> int:
    sql = "SELECT COUNT(*) FROM t_poi WHERE ticket_price IS NULL OR ticket_price = 0"
    args: list = []
    if city:
        sql += " AND city_name = %s"
        args.append(city)
    with conn.cursor() as cur:
        cur.execute(sql, args)
        return int(cur.fetchone()[0])


def apply_update(conn, poi: PoiRow, price: Decimal) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE t_poi SET ticket_price = %s WHERE id = %s",
            (str(price), poi.id),
        )
    conn.commit()


def run(args) -> int:
    amap_key = args.amap_key or os.getenv("AMAP_WEB_API_KEY")
    if not amap_key:
        print("[错误] 未提供高德 Web 服务 Key：请设置环境变量 AMAP_WEB_API_KEY 或传 --amap-key")
        return 2

    import pymysql

    try:
        conn = pymysql.connect(charset="utf8mb4", **DEFAULT_DB)
    except Exception as e:  # noqa: BLE001
        print(f"[错误] 数据库连接失败: {e}")
        print(f"       连接参数: {DEFAULT_DB['user']}@{DEFAULT_DB['host']}:{DEFAULT_DB['port']}/{DEFAULT_DB['database']}")
        return 2

    try:
        missing = count_missing(conn, args.city)
        pois = load_pois_to_fill(conn, args.city)
        print(f"[信息] 待补库景点数: {len(pois)}（库中 ticket_price 为空/0 共 {missing} 条"
              + (f"，限定城市={args.city}" if args.city else "") + "）")
        if not pois:
            print("[完成] 没有需要补库的景点。")
            return 0

        stats = Stats(total=len(pois))
        for idx, poi in enumerate(pois, start=1):
            price, amap_name, note = query_amap_ticket(poi.poi_name, poi.city_name, amap_key)
            time.sleep(REQUEST_INTERVAL_SECONDS)

            if price is not None:
                kind = "免费" if price == 0 else f"{price}元"
                print(f"[{idx}/{len(pois)}] {poi.city_name}/{poi.poi_name} -> {amap_name} | {kind}")
                if price == 0:
                    stats.free += 1
                else:
                    stats.filled += 1
                if args.apply:
                    apply_update(conn, poi, price)
                else:
                    print("           (dry-run，未写库；加 --apply 后生效)")
            else:
                if "API请求失败" in note or "API返回异常" in note:
                    stats.api_error += 1
                elif "无此POI" in note:
                    stats.not_found += 1
                else:
                    stats.no_cost_data += 1
                print(f"[{idx}/{len(pois)}] {poi.city_name}/{poi.poi_name} -> 跳过（{note}）")

            stats.details.append(BackfillResult(poi=poi, price=price, amap_name=amap_name, note=note))

        print("\n========== 补库报告 ==========")
        print(f"待处理: {stats.total}")
        print(f"已写入真实票价: {stats.filled}")
        print(f"已写入免费(0元): {stats.free}")
        print(f"高德无此POI: {stats.not_found}")
        print(f"高德未提供票价(cost为空): {stats.no_cost_data}")
        print(f"API异常: {stats.api_error}")
        print(f"模式: {'APPLY(已写库)' if args.apply else 'DRY-RUN(未写库)'}")
        print("==============================")
        if stats.filled + stats.free == 0:
            print("\n[说明] 当前高德 Key 未返回任何票价数据（biz_ext.cost 全为空）。")
            print("       该字段需要高德商业数据权限；未开通前这些景点在预算引擎中")
            print("       会按『POI库均价 -> 系统估算』降级，并在界面标注价格来源。")
        return 0
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="高德 POI 门票价格补库脚本")
    parser.add_argument("--apply", action="store_true", help="实际写入数据库（默认仅预演 dry-run）")
    parser.add_argument("--city", help="只补指定城市，如：杭州")
    parser.add_argument("--amap-key", help="高德 Web 服务 Key（默认读环境变量 AMAP_WEB_API_KEY）")
    args = parser.parse_args()
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
