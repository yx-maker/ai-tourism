# -*- coding: utf-8 -*-
"""
景点库补录：从高德 Web 服务 API 抓取城市景点并写入 t_poi。

背景：景点库（t_poi）原先只收录 26 个城市，用户查询未收录城市（如福州）时
POI 检索返回 0 条，规划模型失去事实支撑，会凭常识串到其他城市的著名景点
（实测福州行程里冒出「杭州西湖」）。本脚本用于扩充城市景点数据，支持单城与全国批量。

用法：
    # 单城（预览 / 写库）
    python fetch_poi_by_city.py --city 福州 --limit 20
    python fetch_poi_by_city.py --city 福州 --limit 20 --apply

    # 全国批量（城市清单来自 cities_cn.json）
    python fetch_poi_by_city.py --all --limit-per-city 20            # 预览统计
    python fetch_poi_by_city.py --all --limit-per-city 20 --apply    # 写库（可中断续跑）
    python fetch_poi_by_city.py --tier 1 --apply                     # 只跑省会/直辖市/热门（82 城）
    python fetch_poi_by_city.py --province 福建省 --apply

说明：
- 城市清单用 adcode（行政区划代码）请求，避免同名城市 / 民族自治州歧义；
  adcode 失败时自动回退城市名。
- **断点续传**：默认跳过 t_poi 中已有 ≥ --limit-per-city 条的城市，中断后重跑不会重复劳动；
  需要覆盖更新时加 --refresh。
- 高德 place API 的 cost 字段对景点基本返回空，因此 ticket_price 取不到时写 0
  （按系统约定 0 = 免费/未查到），绝不臆造票价。
- 已存在的同名同城市景点会跳过，可重复执行。
"""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

import pymysql
import requests

HERE = Path(__file__).parent
CITY_LIST_FILE = HERE / "cities_cn.json"

from amap_env import get_amap_web_key  # noqa: E402  （同目录工具，禁止硬编码 Key）

AMAP_KEY = get_amap_web_key()
AMAP_URL = "https://restapi.amap.com/v3/place/text"

DB = dict(host="127.0.0.1", port=3306, user="root", password="123456",
          database="aitourism", charset="utf8mb4")

# 高德 Web 服务个人版 QPS 有限，批量时保持温和节奏
REQUEST_INTERVAL = 0.35

# 明显不是「可游览景点」的噪声条目
EXCLUDE_KEYWORDS = ["停车场", "出入口", "售票处", "游客服务中心", "卫生间", "公厕",
                    "公交站", "地铁站", "收费站", "服务区", "加油站", "门楼", "牌坊",
                    "管理处", "办事处", "宿舍", "广场舞", "健身"]

# 类型白名单：只保留真正的游览对象
INCLUDE_TYPE_HINTS = ["风景名胜", "公园", "寺庙", "道观", "教堂", "博物馆", "纪念馆",
                      "动物园", "植物园", "水族馆", "海滩", "海滨", "山", "湖",
                      "古迹", "遗址", "园林", "度假", "游乐园", "主题公园", "老街",
                      "古镇", "古村", "塔", "石窟", "湿地", "森林"]


# ---------------------------------------------------------------- 城市清单

def load_cities(tier: Optional[int] = None, province: Optional[str] = None,
                names: Optional[List[str]] = None) -> List[Dict]:
    """从 cities_cn.json 加载城市清单，支持按 tier / province / 名称过滤"""
    if not CITY_LIST_FILE.exists():
        print(f"[error] 城市清单不存在：{CITY_LIST_FILE}\n"
              f"        请先运行：python build_city_list.py", file=sys.stderr)
        sys.exit(1)
    data = json.loads(CITY_LIST_FILE.read_text(encoding="utf-8"))
    cities = data.get("cities") or []
    if tier:
        cities = [c for c in cities if c.get("tier") == tier]
    if province:
        cities = [c for c in cities if province in (c.get("province") or "")]
    if names:
        want = set(names)
        cities = [c for c in cities if c.get("name") in want]
    return cities


# ---------------------------------------------------------------- 抓取

def fetch_pois(city: str, limit: int, adcode: str = "", pages: int = 3) -> List[Dict]:
    """从高德抓取城市景点（按 ratings 排序由 API 侧保证）。

    city 参数优先用 adcode（唯一、无歧义）；adcode 无结果时回退城市名。
    """
    def _query(city_param: str) -> List[Dict]:
        out: List[Dict] = []
        seen = set()
        for page in range(1, pages + 1):
            try:
                r = requests.get(AMAP_URL, params={
                    "key": AMAP_KEY, "keywords": "风景名胜", "city": city_param,
                    "types": "风景名胜", "offset": 25, "page": page,
                    "extensions": "all",
                }, timeout=20)
                data = r.json()
            except Exception as e:  # noqa: BLE001
                print(f"[warn] 第 {page} 页请求失败: {e}")
                continue
            if str(data.get("status")) != "1":
                print(f"[warn] 第 {page} 页返回异常: {data.get('info')}")
                break
            pois = data.get("pois") or []
            if not pois:
                break
            for p in pois:
                name = (p.get("name") or "").strip()
                if not name or name in seen:
                    continue
                if any(k in name for k in EXCLUDE_KEYWORDS):
                    continue
                ptype = p.get("type") or ""
                if not any(h in ptype for h in INCLUDE_TYPE_HINTS):
                    continue
                seen.add(name)
                out.append(p)
            if len(out) >= limit:
                return out[:limit]
            time.sleep(REQUEST_INTERVAL)
        return out

    # 先按 adcode 精确请求
    if adcode:
        got = _query(adcode)
        if got:
            return got
    # 回退：城市名（部分民族自治州 adcode 检索不到）
    return _query(city)


def drop_sub_attractions(pois: List[Dict]) -> List[Dict]:
    """剔除「父景点-子景点」式重复细分条目（如 三坊七巷-衣锦坊）。

    高德常把同一景区的内部小点单独返回，写进景点库会造成行程重复、排名虚高。
    规则：名称含 "-" 且其前缀已在列表中 → 丢弃。
    """
    names = [(p.get("name") or "").strip() for p in pois]
    keep = []
    for p, name in zip(pois, names):
        if "-" in name or "－" in name:
            prefix = re.split(r"[-－]", name)[0].strip()
            if prefix and any(n == prefix for n in names):
                continue
        keep.append(p)
    return keep


def parse_poi(p: Dict, city: str, rank_city: int, rank_china_base: int) -> Optional[Dict]:
    loc = (p.get("location") or "").split(",")
    if len(loc) != 2:
        return None
    try:
        lng, lat = round(float(loc[0]), 6), round(float(loc[1]), 6)
    except ValueError:
        return None

    biz = p.get("biz_ext") or {}
    cost = biz.get("cost")
    try:
        ticket = float(cost) if cost not in (None, "", [], "[]") else 0.0
    except (TypeError, ValueError):
        ticket = 0.0

    # 描述：高德不返回人文简介，用结构化事实（类型/评分/开放时间）代替，避免编造
    seg = [s for s in (p.get("type") or "").split(";") if s]
    subtype = seg[-1] if seg else "景点"
    rating = biz.get("rating") or ""
    open_time = biz.get("opentime2") or biz.get("open_time") or ""
    if isinstance(open_time, list):
        open_time = ""
    desc_parts = [subtype]
    if rating:
        desc_parts.append(f"评分 {rating}")
    if open_time:
        desc_parts.append(f"开放时间 {open_time[:40]}")
    desc = " · ".join(desc_parts)[:200]

    return {
        "poi_name": (p.get("name") or "").strip(),
        "city_name": city,
        "poi_description": desc,
        "poi_longitude": lng,
        "poi_latitude": lat,
        "poi_rankInCity": rank_city,
        "poi_rankInChina": rank_china_base + rank_city,
        "ticket_price": ticket,
    }


INSERT_SQL = ("INSERT INTO t_poi (poi_name, city_name, poi_description, "
              "poi_longitude, poi_latitude, poi_rankInCity, poi_rankInChina, "
              "ticket_price, created_time, modify_time) VALUES "
              "(%(poi_name)s, %(city_name)s, %(poi_description)s, %(poi_longitude)s, "
              "%(poi_latitude)s, %(poi_rankInCity)s, %(poi_rankInChina)s, "
              "%(ticket_price)s, NOW(), NOW())")


# ---------------------------------------------------------------- 单城流程

def process_city(conn, city: Dict, limit: int, apply: bool, verbose: bool) -> int:
    """处理单个城市，返回新增条数"""
    name, adcode = city["name"], city.get("adcode", "")
    with conn.cursor() as cur:
        cur.execute("SELECT IFNULL(MAX(poi_rankInChina), 0) FROM t_poi")
        rank_base = cur.fetchone()[0] or 0
        cur.execute("SELECT poi_name FROM t_poi WHERE city_name=%s", (name,))
        existing = {r[0] for r in cur.fetchall()}

    pois = drop_sub_attractions(fetch_pois(name, limit, adcode=adcode))
    if not pois:
        return 0

    rows = []
    for i, p in enumerate(pois, start=1):
        row = parse_poi(p, name, i, rank_base)
        if row:
            rows.append(row)

    todo = [r for r in rows if r["poi_name"] not in existing]
    if verbose:
        print(f"\n── {name}（{city.get('province','')}）抓取 {len(rows)} 条，已有 {len(existing)} 条，"
              f"待插入 {len(todo)} 条")
        for r in todo:
            print(f"  {r['poi_rankInCity']:>2}. {r['poi_name']:<16} "
                  f"票价={r['ticket_price']:<6} 坐标=({r['poi_longitude']},{r['poi_latitude']})")
            print(f"      {r['poi_description']}")

    if not apply or not todo:
        return len(todo)

    with conn.cursor() as cur:
        cur.executemany(INSERT_SQL, todo)
    conn.commit()
    return len(todo)


# ---------------------------------------------------------------- 主流程

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", help="单个城市名，如 福州（与 --all 互斥）")
    ap.add_argument("--all", action="store_true", help="遍历全国城市清单")
    ap.add_argument("--tier", type=int, choices=[1, 2],
                    help="只跑指定层级（1=省会/直辖市/热门 82 城；2=其他地级市）")
    ap.add_argument("--province", help="只跑指定省份，如 福建省")
    ap.add_argument("--limit", type=int, default=20, help="单城模式抓取条数")
    ap.add_argument("--limit-per-city", type=int, default=20, help="批量模式每城抓取条数")
    ap.add_argument("--refresh", action="store_true",
                    help="忽略「该城已有数据」跳过逻辑，强制重新抓取")
    ap.add_argument("--apply", action="store_true", help="真正写入数据库（默认只预览）")
    args = ap.parse_args()

    if not args.city and not (args.all or args.tier or args.province):
        ap.error("需指定 --city，或 --all / --tier / --province 之一")

    # ---- 批量：全国 / 分层 / 分省 ----
    if not args.city:
        cities = load_cities(tier=args.tier, province=args.province)
        if not cities:
            print("[error] 过滤后没有城市，请检查 --tier / --province")
            sys.exit(1)

        conn = pymysql.connect(**DB)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT city_name, COUNT(*) FROM t_poi GROUP BY city_name")
                have = {r[0]: r[1] for r in cur.fetchall()}

            total_added = 0
            skipped = 0
            failed: List[str] = []
            print(f"批量景点补录：{len(cities)} 城，每城上限 {args.limit_per_city} 条"
                  f"{'（写库）' if args.apply else '（预览）'}")
            if not args.refresh:
                print("断点续传：已有足够数据的城市自动跳过（加 --refresh 覆盖）\n")

            for i, c in enumerate(cities, start=1):
                name = c["name"]
                if not args.refresh and have.get(name, 0) >= args.limit_per_city:
                    skipped += 1
                    continue
                try:
                    n = process_city(conn, c, args.limit_per_city, args.apply, verbose=False)
                    total_added += n
                    print(f"[{i}/{len(cities)}] {name:<8} 新增 {n}")
                except Exception as e:  # noqa: BLE001
                    failed.append(name)
                    print(f"[{i}/{len(cities)}] {name:<8} 失败：{type(e).__name__}: {e}")
                time.sleep(REQUEST_INTERVAL)

            print(f"\n===== 完成 =====")
            print(f"  处理城市：{len(cities) - skipped}（跳过已有数据 {skipped}）")
            print(f"  新增景点：{total_added}")
            if failed:
                print(f"  失败城市：{len(failed)} → {failed[:15]}")
            if not args.apply:
                print("\n[预览模式] 加 --apply 才会写库")
        finally:
            conn.close()
        return

    # ---- 单城 ----
    city_rec = {"name": args.city, "adcode": "", "province": ""}
    for c in load_cities(names=[args.city]):
        city_rec = c
        break
    conn = pymysql.connect(**DB)
    try:
        n = process_city(conn, city_rec, args.limit, args.apply, verbose=True)
        if args.apply:
            print(f"\n✅ 已写入 {n} 条到 t_poi")
        else:
            print("\n[预览模式] 加 --apply 才会写库")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
