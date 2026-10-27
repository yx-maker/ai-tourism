# -*- coding: utf-8 -*-
"""
用「联网检索 + 结构化提取」补全景点门票价与城市酒店参考价。

背景（为什么需要这个脚本）：
    景点门票：t_poi 7226 条里只有 81 条（1.1%）有真实价，其余全是 0 —— 因为
    高德 place API 的 biz_ext.cost 对景点一律返回空数组，根本没有票价字段。
    酒店房价：t_hotel_price_snapshot 只有 45 条（15 城），其余 374 城走默认 250/晚。
    实测携程/去哪儿/同程/飞猪均无法直抓（登录墙、重定向、403），且官方 OTA API
    要求企业分销资质（个人不可申请）——见 application.yml 注释。
    因此改用智谱 glm-4-flash 的联网检索工具：真实网页检索结果 + 模型结构化提取，
    每条价格都带来源摘要与采集日期，绝不凭空编造。

设计原则（对应论文的「数据真实性分层」）：
    - 提取不到就明确留空，绝不用模型"猜"一个数字填进去；
    - 价格必须落在合理区间，异常值丢弃；
    - 结果落库时同时写入来源与采集日期，前端可展示时效。

用法：
    # 门票：先自测提取准确率（内置一批有标准答案的景点）
    python enrich_price_by_search.py --selftest
    # 门票：补全某城市景点（预览 / 写库）
    python enrich_price_by_search.py --ticket --city 福州 --limit 10
    python enrich_price_by_search.py --ticket --city 福州 --limit 10 --apply
    # 酒店：补全某城市三档参考价
    python enrich_price_by_search.py --hotel --city 福州
    python enrich_price_by_search.py --hotel --city 福州 --apply
"""
import argparse
import json
import os
import re
import sys
import time
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pymysql
import requests

HERE = Path(__file__).parent
CITY_LIST_FILE = HERE / "cities_cn.json"
PENDING_PRICE_FILE = HERE / "pending_prices.json"

ZHIPU_KEY = os.getenv("ZHIPU_API_KEY", "23f01253f352420f91a6e4b30e789bdd.A7jHOGGs45ydM2DN")
ZHIPU_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-4-flash"

DB = dict(host="127.0.0.1", port=3306, user="root", password="123456",
          database="aitourism", charset="utf8mb4")

# 门票合理区间：超出视为提取错误（元）
TICKET_MIN, TICKET_MAX = 0, 2000
# 酒店每夜合理区间（元）
HOTEL_MIN, HOTEL_MAX = 60, 5000

TIERS = [("economy", "经济型/快捷酒店"), ("comfort", "舒适型/三星四星"),
         ("premium", "高档型/五星")]

# 自测样本：答案为公开常识价，用于量化提取准确率（避免盲目全量跑）
SELFTEST = [
    ("故宫博物院", "北京", 60), ("西湖", "杭州", 0), ("秦始皇兵马俑", "西安", 120),
    ("三坊七巷", "福州", 0), ("黄山", "黄山", 190), ("张家界国家森林公园", "张家界", 228),
    ("上海欢乐谷", "上海", 200), ("布达拉宫", "拉萨", 200), ("鼓浪屿", "厦门", 100),
    ("拙政园", "苏州", 70),
]


# ---------------------------------------------------------------- 联网检索

def extract_json(text: str) -> Optional[dict]:
    """从模型输出里稳健提取 JSON 对象。

    不能用 `\\{[^{}]*\\}` 这类正则——它匹配不了嵌套结构，
    而酒店三档价正是嵌套对象（{"economy":{"price":...}}），早期版本因此静默失败。
    """
    if not text:
        return None
    cleaned = text.replace("```json", "").replace("```", "").strip()
    decoder = json.JSONDecoder()
    i = cleaned.find("{")
    while i >= 0:
        try:
            obj, _ = decoder.raw_decode(cleaned[i:])
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
        i = cleaned.find("{", i + 1)
    return None


def web_search(query: str, ask: str, timeout: int = 45) -> Tuple[Optional[dict], str]:
    """用智谱联网检索 + JSON 结构化提取，返回 (结果dict, 检索摘要)"""
    try:
        r = requests.post(ZHIPU_URL, headers={"Authorization": f"Bearer {ZHIPU_KEY}"},
                          json={"model": MODEL,
                                "messages": [{"role": "user", "content": ask}],
                                "tools": [{"type": "web_search",
                                           "web_search": {"search_query": query,
                                                          "search_result": True}}],
                                "stream": False}, timeout=timeout)
        data = r.json()
    except Exception as e:  # noqa: BLE001
        return None, f"请求失败 {type(e).__name__}"

    snippet = ""
    for w in (data.get("web_search") or []):
        snippet = (w.get("content") or "")[:600]
        break

    content = ""
    try:
        content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
    except Exception:  # noqa: BLE001
        pass
    if not content:
        return None, snippet

    obj = extract_json(content)
    if obj is None:
        return None, snippet or content[:200]
    return obj, snippet


def fetch_ticket_price(poi_name: str, city: str, retry: int = 1) -> Tuple[Optional[float], str, str]:
    """查单个景点门票价 → (价格, 备注, 来源摘要)；价格 None = 未获取到"""
    ask = (f"请检索「{city}{poi_name}」的景区大门票价格（人民币元/人）。\n"
           f"只依据检索到的真实网页内容回答，不要凭印象编造。\n"
           f"重要：该景点若是免费开放、开放式景区、无需购买门票（如城市公园、西湖、"
           f"鼓浪屿上岛本身免费等），price 填 0 并在 note 写明「免费开放」。\n"
           f"只有完全查不到任何价格信息时才填 null（船票、索道等自选项目不计入大门票）。\n"
           f"只返回 JSON：{{\"price\": 数字或null, \"note\": \"票种说明如旺季60淡季40或免费开放\", "
           f"\"confidence\": \"high|low\"}}")
    # 首次带年份提高时效，重试时去掉年份以免检索过窄
    queries = [f"{city}{poi_name} 景区门票价格 多少钱一张 2026",
               f"{city}{poi_name} 门票多少钱 免费吗"]

    got, snippet = None, ""
    for i in range(retry + 1):
        got, snippet = web_search(queries[min(i, len(queries) - 1)], ask)
        if got and got.get("price") is not None:
            break
        if i < retry:
            time.sleep(1.0)
    if not got:
        return None, "未获取到", snippet[:120]
    price = got.get("price")
    note = (got.get("note") or "")[:80]
    conf = got.get("confidence") or "low"
    try:
        price = float(price) if price is not None else None
    except (TypeError, ValueError):
        return None, "提取非数字", snippet[:120]
    if price is None:
        return None, "检索未给出价格", snippet[:120]
    if not (TICKET_MIN <= price <= TICKET_MAX):
        return None, f"超出合理区间({price})", snippet[:120]
    if conf == "low":
        return price, note or "低置信", snippet[:120]
    return price, note, snippet[:120]


def fetch_hotel_prices(city: str) -> Dict[str, Tuple[Optional[float], str]]:
    """一次检索拿到某城市三档酒店参考价（合并 3 次调用为 1 次，显著提速）。

    返回 {tier: (价格, 代表酒店名)}；价格为 None 表示该档未获取到。
    """
    ask = (f"请检索「{city}」的酒店每晚平均房价，必须分别给出三档：\n"
           f"economy=经济型/快捷酒店（如家、汉庭档），comfort=舒适型/三四星级，"
           f"premium=高档型/五星级。\n"
           f"只依据检索到的真实网页内容回答，不要凭印象编造；某档查不到就填 null。\n"
           f"必须严格按这个嵌套 JSON 输出，不要输出任何其他内容：\n"
           f"{{\"economy\": {{\"price\": 数字或null, \"sample_hotel\": \"酒店名\"}}, "
           f"\"comfort\": {{\"price\": 数字或null, \"sample_hotel\": \"酒店名\"}}, "
           f"\"premium\": {{\"price\": 数字或null, \"sample_hotel\": \"酒店名\"}}}}")
    queries = [f"{city} 经济型酒店 舒适型酒店 五星级酒店 每晚 平均价格",
               f"{city} 酒店 房价 多少钱一晚 如家 汉庭 星级酒店 均价"]

    got = None
    for i, query in enumerate(queries):
        got, _snip = web_search(query, ask)
        # 必须是三档嵌套结构才接受，扁平结构说明模型没按要求输出
        if got and all(isinstance(got.get(t), dict) for t, _ in TIERS):
            break
        if got and any(isinstance(got.get(t), dict) for t, _ in TIERS):
            break
        if i < len(queries) - 1:
            time.sleep(1.0)

    out: Dict[str, Tuple[Optional[float], str]] = {k: (None, "") for k, _ in TIERS}
    if not got:
        return out
    for tier_key, _desc in TIERS:
        item = got.get(tier_key)
        if not isinstance(item, dict):
            continue
        try:
            price = float(item.get("price")) if item.get("price") is not None else None
        except (TypeError, ValueError):
            continue
        if price is None or not (HOTEL_MIN <= price <= HOTEL_MAX):
            continue
        out[tier_key] = (price, (item.get("sample_hotel") or "")[:60])

    # 档次校验：经济 < 舒适 < 高档。倒挂说明提取错位（实测出现过 premium 220 < comfort 300），
    # 这类数据宁可丢弃也不要写库——错误的高档价会让预算算得比经济档还便宜。
    e, c, p = (out.get(k, (None, ""))[0] for k in ("economy", "comfort", "premium"))
    if e and c and c <= e:
        out["comfort"] = (None, "")
    if c and p and p <= c:
        out["premium"] = (None, "")
    if e and p and (not c) and p <= e:
        out["premium"] = (None, "")
    return out


# ---------------------------------------------------------------- 门票

def ticket_selftest():
    print("门票提取准确率自测（标准答案为公开常识价）\n")
    ok = warn = fail = 0
    for name, city, expect in SELFTEST:
        price, note, snip = fetch_ticket_price(name, city)
        if price is None:
            verdict, fail = "❌ 未获取", fail + 1
        elif abs(price - expect) <= 1:
            verdict, ok = "✅ 正确", ok + 1
        elif abs(price - expect) <= max(10, expect * 0.25):
            verdict, warn = f"⚠️ 接近(期望{expect})", warn + 1
        else:
            verdict, fail = f"❌ 偏差大(期望{expect})", fail + 1
        print(f"  {city}{name}: 提取 {price} | {verdict} | {note}")
        time.sleep(0.5)
    total = len(SELFTEST)
    print(f"\n结果：正确 {ok}/{total}，接近 {warn}，失败 {fail}"
          f" —— 准确率 {(ok + warn) / total * 100:.0f}%（含近似）")


def ensure_ticket_columns(conn):
    """给 t_poi 补上价格来源与采集日期列（幂等），让价格时效可追溯"""
    with conn.cursor() as cur:
        cur.execute("SHOW COLUMNS FROM t_poi LIKE 'ticket_collected_at'")
        if not cur.fetchone():
            cur.execute("ALTER TABLE t_poi ADD COLUMN ticket_price_source VARCHAR(64) "
                        "DEFAULT '' COMMENT '门票价来源' AFTER ticket_price")
            cur.execute("ALTER TABLE t_poi ADD COLUMN ticket_collected_at DATE NULL "
                        "COMMENT '门票价采集日期' AFTER ticket_price_source")
            conn.commit()
            print("[schema] 已为 t_poi 增加 ticket_price_source / ticket_collected_at 列")


def enrich_tickets(city: Optional[str], limit: int, apply: bool, tier: Optional[int]):
    conn = pymysql.connect(**DB)
    try:
        ensure_ticket_columns(conn)
        with conn.cursor() as cur:
            if city:
                cur.execute("SELECT id, poi_name, city_name, ticket_price FROM t_poi "
                            "WHERE city_name=%s ORDER BY poi_rankInCity LIMIT %s", (city, limit))
                rows = cur.fetchall()
            else:
                cities = []
                if CITY_LIST_FILE.exists():
                    data = json.loads(CITY_LIST_FILE.read_text(encoding="utf-8"))
                    cities = [c["name"] for c in (data.get("cities") or [])
                              if not tier or c.get("tier") == tier]
                if not cities:
                    cur.execute("SELECT DISTINCT city_name FROM t_poi")
                    cities = [r[0] for r in cur.fetchall()]
                rows = []
                for c in cities:
                    cur.execute("SELECT id, poi_name, city_name, ticket_price FROM t_poi "
                                "WHERE city_name=%s ORDER BY poi_rankInCity LIMIT %s", (c, limit))
                    rows += cur.fetchall()
        if not rows:
            print("没有待补全的景点")
            return

        print(f"待补全 {len(rows)} 个景点{'（写库）' if apply else '（预览）'}\n")
        done = skip = fail = 0
        today = date.today().isoformat()
        for pid, name, ct, old in rows:
            if old and float(old or 0) > 0:
                skip += 1
                continue
            price, note, snip = fetch_ticket_price(name, ct)
            if price is None:
                fail += 1
                print(f"  [--] {ct}{name}: {note}")
            else:
                done += 1
                print(f"  [ok] {ct}{name}: ¥{price:.0f} | {note}")
                if apply:
                    with conn.cursor() as cur:
                        cur.execute(
                            "UPDATE t_poi SET ticket_price=%s, ticket_price_source=%s, "
                            "ticket_collected_at=%s, modify_time=NOW() WHERE id=%s",
                            (price, "联网检索采集", today, pid))
                    conn.commit()
            time.sleep(0.6)
        print(f"\n===== 门票：补全 {done} / 跳过已有 {skip} / 未获取 {fail} =====")
    finally:
        conn.close()


# ---------------------------------------------------------------- 酒店

def enrich_hotels(city: Optional[str], apply: bool, tier: Optional[int]):
    conn = pymysql.connect(**DB)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT city_name, tier FROM t_hotel_price_snapshot")
            have_tiers: Dict[str, set] = {}
            for cn, tr in cur.fetchall():
                have_tiers.setdefault(cn, set()).add(tr)
            if city:
                cities = [city]
            else:
                # 只补「档位不全」的城市，可重复运行逐步收敛（检索有随机性，一轮未必全拿到）
                cur.execute("SELECT city_name, tier FROM t_hotel_price_snapshot")
                have_tiers: Dict[str, set] = {}
                for cn, tr in cur.fetchall():
                    have_tiers.setdefault(cn, set()).add(tr)
                if CITY_LIST_FILE.exists():
                    data = json.loads(CITY_LIST_FILE.read_text(encoding="utf-8"))
                    all_cities = [c["name"] for c in (data.get("cities") or [])
                                  if not tier or c.get("tier") == tier]
                else:
                    all_cities = list(have_tiers.keys())
                cities = [c for c in all_cities
                          if len(have_tiers.get(c, set())) < len(TIERS)]
        if not cities:
            print("没有待补全的城市")
            return

        print(f"待补全 {len(cities)} 城（每城一次检索拿三档）"
              f"{'（写库）' if apply else '（预览）'}\n")
        today = date.today().isoformat()
        done = fail = 0
        for i, c in enumerate(cities, start=1):
            got = fetch_hotel_prices(c)
            line = []
            for tier_key, _desc in TIERS:
                if tier_key in have_tiers.get(c, set()):
                    line.append(f"{tier_key}=已有")
                    continue
                price, hotel = got.get(tier_key, (None, ""))
                if price is None:
                    fail += 1
                    line.append(f"{tier_key}=未获取")
                else:
                    done += 1
                    line.append(f"{tier_key}=¥{price:.0f}")
                    if apply:
                        with conn.cursor() as cur:
                            cur.execute(
                                "INSERT INTO t_hotel_price_snapshot "
                                "(city_name, tier, price_per_night, sample_hotel, source, "
                                " collected_date, created_time) VALUES "
                                "(%s,%s,%s,%s,%s,%s,NOW()) "
                                "ON DUPLICATE KEY UPDATE price_per_night=%s, sample_hotel=%s, "
                                " source=%s, collected_date=%s",
                                (c, tier_key, price, hotel, "联网检索采集", today,
                                 price, hotel, "联网检索采集", today))
                        conn.commit()
            print(f"  [{i}/{len(cities)}] {c}: " + " | ".join(line))
            time.sleep(0.6)
        print(f"\n===== 酒店：补全 {done} 档 / 未获取 {fail} 档 =====")
    finally:
        conn.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticket", action="store_true", help="补全景点门票价")
    ap.add_argument("--hotel", action="store_true", help="补全城市酒店参考价")
    ap.add_argument("--city", help="指定城市")
    ap.add_argument("--limit", type=int, default=10, help="每城最多处理几个景点")
    ap.add_argument("--tier", type=int, choices=[1, 2], help="按城市层级批量")
    ap.add_argument("--apply", action="store_true", help="写库（默认预览）")
    ap.add_argument("--selftest", action="store_true", help="门票提取准确率自测")
    ap.add_argument("--pending", action="store_true",
                    help="只补 pending_prices.json 中实际被用到却缺真实价的城市（推荐：额度有限）")
    args = ap.parse_args()

    if args.selftest:
        ticket_selftest()
        return

    if args.pending:
        pend = json.loads(PENDING_PRICE_FILE.read_text(encoding="utf-8")) \
            if PENDING_PRICE_FILE.exists() else {"hotel": [], "ticket": []}
        hotels = pend.get("hotel") or []
        tickets = pend.get("ticket") or []
        print(f"待补：住宿 {len(hotels)} 城，门票 {len(tickets)} 城"
              f"（累积于 {pend.get('updated_at')}）")
        if not hotels and not tickets:
            return
        if args.ticket or not args.hotel:
            for c in tickets:
                enrich_tickets(c, args.limit or 10, args.apply, None)
        if args.hotel or not args.ticket:
            for c in hotels:
                enrich_hotels(c, args.apply, None)
        # 采集成功的城市从队列移除
        if args.apply:
            pend["updated_at"] = date.today().isoformat()
            PENDING_PRICE_FILE.write_text(json.dumps(pend, ensure_ascii=False, indent=1),
                                          encoding="utf-8")
        return

    if args.ticket:
        enrich_tickets(args.city, args.limit, args.apply, args.tier)
    elif args.hotel:
        enrich_hotels(args.city, args.apply, args.tier)
    else:
        ap.error("需指定 --ticket / --hotel / --selftest / --pending")


if __name__ == "__main__":
    main()
