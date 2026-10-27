# -*- coding: utf-8 -*-
"""
12306 票价高速抓取（纯 HTTP，无需浏览器）—— 全国任意城市对的实时票价。

为什么要单独做这个脚本：
    原 scrape_train_fares.py 用浏览器逐对渲染页面，每对需 12~18 秒。
    全国 391 城两两组合 = 76,245 对，按此速度需连续跑 9 天以上，工程上不可行，
    于是票价只能预爬少数热门城市，未收录城市降级为「系数估算」——这正是用户
    反馈「车票不准」的根源。

    12306 的余票查询与票价查询实际是两个轻量 JSON 接口，可直接 HTTP 调用：
      GET /otn/leftTicket/query           → 车次列表（含 train_no / 席别码）
      GET /otn/leftTicket/queryTicketPrice → 该车次各席别实时票价
    单对约 1~3 秒，比浏览器快一个数量级，使「全国 tier1 全量 + 按需补抓」成为可行动方案。

关键坑（已踩过）：
    query 返回的 result 是 '|' 分隔的字符串数组，索引 2 才是真正的 train_no
    （如 '6c000G301700'），索引 3 是展示用的车次号（'G3017'）。
    用索引 3 调 queryTicketPrice 会返回空 data，静默拿不到价格。

用法：
    python fetch_train_price_http.py --pair 广州 福州        # 按需查单对（立即返回）
    python fetch_train_price_http.py --tier 1               # tier1（82 城，3,321 对）增量跑
    python fetch_train_price_http.py --pending              # 补抓累积的缺失城市对
    python fetch_train_price_http.py --cities 厦门 泉州      # 指定城市两两组合
    python fetch_train_price_http.py --all                  # 全部 391 城（组合数巨大，需确认）
    python fetch_train_price_http.py --force                # 忽略缓存强制重抓

输出：captured/train_price.json（与浏览器版同格式，可直接喂给 build_local_price_resource.py）
"""
import argparse
import itertools
import json
import random
import re
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests

HERE = Path(__file__).parent
OUT_FILE = HERE / "captured" / "train_price.json"
CITY_LIST_FILE = HERE / "cities_cn.json"
PENDING_FILE = HERE / "pending_pairs.json"
STATION_JS = "https://kyfw.12306.cn/otn/resources/js/framework/station_name.js"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# 席别码 → 中文（12306 约定）
SEAT_MAP = {
    "A9": "商务座", "A6": "高级软卧", "A4": "软卧", "A3": "硬卧",
    "A2": "软座", "A1": "硬座", "M": "一等座", "O": "二等座",
    "WZ": "无座", "A5": "包厢硬卧",
}

# query result 的 '|' 分隔字段索引
IDX_TRAIN_NO = 2        # 真正用于查价的 train_no
IDX_TRAIN_CODE = 3      # 展示用车次号（G3017）
IDX_FROM_STATION_NO = 16
IDX_TO_STATION_NO = 17
IDX_SEAT_TYPES = 35


# ---------------------------------------------------------------- 基础

def new_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": UA,
                      "Referer": "https://kyfw.12306.cn/otn/leftTicket/init"})
    try:
        s.get("https://kyfw.12306.cn/otn/leftTicket/init", timeout=15)
    except Exception as e:  # noqa: BLE001
        print(f"[warn] init 失败（不影响后续）: {e}")
    return s


def fetch_station_codes(s: requests.Session) -> Dict[str, str]:
    """站名 → 电报码（3400+ 站）"""
    r = s.get(STATION_JS, timeout=30)
    text = r.text
    codes: Dict[str, str] = {}
    for m in re.finditer(r"\|([^|]+)\|([A-Z]{3})\|[^|]+\|[^|]+\|(\d)", text):
        codes.setdefault(m.group(1), m.group(2))
    return codes


def resolve_station_candidates(city: str, codes: Dict[str, str],
                               limit: int = 3) -> List[Tuple[str, str]]:
    """城市名 → 候选车站列表 [(电报码, 站名)]，按优先级排序。

    为什么要多个候选：部分老站已不办客运，12306 对该站查询会返回 HTML 错误页
    而非 JSON（实测「开封」KFF 返回 HTML，而「开封北」KBF 正常）。
    只取第一个站会导致整条线路静默失败，故保留多个候选供逐级回退。
    """
    if not city:
        return []
    out: List[Tuple[str, str]] = []
    if city in codes:
        out.append((codes[city], city))
    for name, code in codes.items():
        if name.startswith(city) and name != city:
            out.append((code, name))
        if len(out) >= limit:
            break
    return out


def load_cities(tier: Optional[int] = None) -> List[str]:
    if not CITY_LIST_FILE.exists():
        print(f"[error] 城市清单不存在：{CITY_LIST_FILE}，请先运行 build_city_list.py",
              file=sys.stderr)
        sys.exit(1)
    data = json.loads(CITY_LIST_FILE.read_text(encoding="utf-8"))
    cities = data.get("cities") or []
    if tier:
        cities = [c for c in cities if c.get("tier") == tier]
    return [c["name"] for c in cities if c.get("name")]


def load_result() -> dict:
    if OUT_FILE.exists():
        return json.loads(OUT_FILE.read_text(encoding="utf-8"))
    return {}


def save_result(r: dict):
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")


# ---------------------------------------------------------------- 核心抓取

def query_trains(s: requests.Session, from_code: str, to_code: str,
                 train_date: str) -> List[List[str]]:
    """查询车次列表，返回字段数组列表"""
    try:
        r = s.get("https://kyfw.12306.cn/otn/leftTicket/query", params={
            "leftTicketDTO.train_date": train_date,
            "leftTicketDTO.from_station": from_code,
            "leftTicketDTO.to_station": to_code,
            "purpose_codes": "ADULT",
        }, timeout=20)
        j = r.json()
    except Exception as e:  # noqa: BLE001
        return [["_error", f"query:{type(e).__name__}"]]
    result = (j.get("data") or {}).get("result") or []
    return [row.split("|") for row in result]


def query_price(s: requests.Session, fields: List[str], train_date: str) -> Dict[str, float]:
    """查单趟车的各席别票价 → {中文席别: 价格}"""
    if len(fields) <= IDX_SEAT_TYPES:
        return {}
    try:
        r = s.get("https://kyfw.12306.cn/otn/leftTicket/queryTicketPrice", params={
            "train_no": fields[IDX_TRAIN_NO],
            "from_station_no": fields[IDX_FROM_STATION_NO],
            "to_station_no": fields[IDX_TO_STATION_NO],
            "seat_types": fields[IDX_SEAT_TYPES],
            "train_date": train_date,
        }, timeout=20)
        data = (r.json().get("data") or {})
    except Exception:  # noqa: BLE001
        return {}
    out: Dict[str, float] = {}
    for code, val in data.items():
        if not isinstance(val, str) or not val.startswith("¥"):
            continue
        try:
            price = float(val.replace("¥", "").strip())
        except ValueError:
            continue
        if price <= 0:
            continue
        name = SEAT_MAP.get(code, code)
        # 同席别取最低（不同车次票价不同）
        if name not in out or price < out[name]:
            out[name] = price
    return out


def scrape_pair(s: requests.Session, a: str, b: str, codes: Dict[str, str],
                train_date: str, max_trains: int, sleep: float) -> Optional[dict]:
    """抓取单对城市的最低票价；返回 None 表示无法查询（站码缺失）"""
    a_cands = resolve_station_candidates(a, codes)
    b_cands = resolve_station_candidates(b, codes)
    if not a_cands or not b_cands:
        return None

    # 逐级回退候选站：老站不办客运时换下一个（如 开封 KFF 失败 → 开封北 KBF）
    rows: List[List[str]] = []
    last_err = "no_train"
    used = None
    for (a_code, a_name) in a_cands:
        for (b_code, b_name) in b_cands:
            got = query_trains(s, a_code, b_code, train_date)
            if got and got[0] and got[0][0] == "_error":
                last_err = got[0][1] if len(got[0]) > 1 else "query_failed"
                continue
            if got:
                rows, used = got, (a_name, b_name)
                break
            last_err = "no_train"
        if rows:
            break
    if not rows:
        # 所有候选都查不到车次：区分「真无直通车」与「查询被拒」
        if last_err != "no_train":
            return {"_error": last_err}
        return {"date": train_date, "train_count": 0, "min_price": {}, "trains": []}

    min_price: Dict[str, float] = {}
    sampled = []
    for f in rows[:max_trains]:
        if len(f) <= IDX_SEAT_TYPES:
            continue
        prices = query_price(s, f, train_date)
        if prices:
            sampled.append({"train_code": f[IDX_TRAIN_CODE], "prices": prices})
            for k, v in prices.items():
                if k not in min_price or v < min_price[k]:
                    min_price[k] = v
        time.sleep(sleep)

    return {
        "date": train_date,
        "train_count": len(rows),
        "min_price": min_price,
        "trains": sampled[:5],
    }


# ---------------------------------------------------------------- 主流程

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pair", nargs=2, metavar=("FROM", "TO"), help="按需查单对")
    ap.add_argument("--tier", type=int, choices=[1, 2], help="1=82 城；2=309 城")
    ap.add_argument("--all", action="store_true", help="全部 391 城（组合数巨大）")
    ap.add_argument("--cities", nargs="+", help="指定城市，两两组合")
    ap.add_argument("--pending", action="store_true", help="补抓累积的缺失城市对")
    ap.add_argument("--pairs", type=int, default=0, help="只跑前 N 对")
    ap.add_argument("--max-trains", type=int, default=8,
                    help="每对最多查几趟车（默认 8，越大越准但越慢）")
    ap.add_argument("--sleep", type=float, default=0.25, help="单次查价间隔（秒）")
    ap.add_argument("--force", action="store_true", help="忽略缓存强制重抓")
    args = ap.parse_args()

    train_date = (date.today() + timedelta(days=10)).isoformat()

    # ---- 组装城市对 ----
    if args.pair:
        pairs = [tuple(args.pair)]
    elif args.pending:
        if not PENDING_FILE.exists():
            print("[info] 暂无待抓城市对")
            return
        pend = json.loads(PENDING_FILE.read_text(encoding="utf-8"))
        pairs = [tuple(k.split("-", 1)) for k in (pend.get("pairs") or []) if "-" in k]
        print(f"待抓队列：{len(pairs)} 对（累积于 {pend.get('updated_at')}）")
    elif args.cities:
        pairs = list(itertools.combinations(args.cities, 2))
    else:
        tier = None if args.all else (args.tier or 1)
        cities = load_cities(tier=tier)
        pairs = list(itertools.combinations(cities, 2))
        n = len(pairs)
        print(f"城市 {len(cities)} 个 → {n} 对；预计 {n * (1 + args.max_trains * args.sleep) / 60:.0f} 分钟")
        if n > 5000 and not args.force:
            print(f"[!] 组合过多（{n}），中断可续跑；若确认请加 --force")
            return
    if args.pairs:
        pairs = pairs[: args.pairs]

    result = load_result()
    todo = []
    for a, b in pairs:
        key = f"{a}-{b}"
        if args.force or key not in result or result[key].get("_error"):
            todo.append((a, b))
    print(f"共 {len(pairs)} 对，缓存 {len(result)} 对，本轮待抓 {len(todo)} 对")
    if not todo:
        print("无待抓城市对")
        return

    s = new_session()
    print("拉取站码表……")
    codes = fetch_station_codes(s)
    print(f"站码 {len(codes)} 个")

    ok = empty = fail = 0
    for i, (a, b) in enumerate(todo, start=1):
        key = f"{a}-{b}"
        try:
            got = scrape_pair(s, a, b, codes, train_date, args.max_trains, args.sleep)
        except Exception as e:  # noqa: BLE001
            got = {"_error": f"{type(e).__name__}"}
        if got is None:
            print(f"[{i}/{len(todo)}] {key}: 站码缺失")
            fail += 1
            continue
        result[key] = got
        if got.get("_error"):
            fail += 1
            print(f"[{i}/{len(todo)}] {key}: 失败 {got['_error']}")
        elif not got.get("min_price"):
            empty += 1
            print(f"[{i}/{len(todo)}] {key}: 无直通车")
        else:
            ok += 1
            mp = got["min_price"]
            brief = " ".join(f"{k}{v:.0f}" for k, v in
                             sorted(mp.items(), key=lambda x: x[1])[:3])
            print(f"[{i}/{len(todo)}] {key}: {got['train_count']}趟 | {brief}")
        if i % 20 == 0:
            save_result(result)
        time.sleep(random.uniform(0.5, 1.2))

    save_result(result)

    if args.pending:
        pend = json.loads(PENDING_FILE.read_text(encoding="utf-8"))
        rest = [k for k in (pend.get("pairs") or [])
                if not (result.get(k) and not result[k].get("_error"))]
        PENDING_FILE.write_text(json.dumps({"pairs": rest, "updated_at": train_date},
                                           ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"待抓队列剩余 {len(rest)} 对")

    print(f"\n===== 完成：成功 {ok} / 无直通车 {empty} / 失败 {fail} "
          f"→ {len(result)} 对已缓存 =====")
    print("提示：同步到 Java 票价表请运行：python build_local_price_resource.py（随后需重启 Java）")


if __name__ == "__main__":
    main()
