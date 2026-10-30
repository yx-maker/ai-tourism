# -*- coding: utf-8 -*-
"""按「车次」绑定票价与历时——彻底消除「便宜票价 + 高铁时长」的错配。

背景（真实故障）：
    旧方案把票价与时长分成两张表抓：
      · 票价表按「城市对 + 席别」跨车次取最低价 → 广州-长沙 二等座 = ¥122
        （那其实是 D 字头动集的价，历时 7~8 小时）
      · 时长表按「高铁动车 / 普速」取最快车次  → 广州-长沙 高铁 = G6018 1h57m
    两者一拼，就成了「¥122 的二等座能 2 小时到长沙」——现实中不存在。

正确做法：
    同一趟车（train_code）同时取「官方历时」和「该车的各席别票价」，
    数据结构天然自洽：选了这趟车的二等座，时长就一定是这趟车的历时。

用法：
    python fetch_train_binding_http.py --limit 5          # 冒烟
    python fetch_train_binding_http.py --pending          # 续跑未完成的
    python fetch_train_binding_http.py                    # 全量
"""
from __future__ import annotations

import argparse
import json
import random
import re
import time
from pathlib import Path
from typing import Dict, List, Optional

from fetch_train_price_http import (  # 复用已验证的会话/站码/查询逻辑
    IDX_SEAT_TYPES,
    IDX_TRAIN_NO,
    fetch_station_codes,
    load_cities,
    new_session,
    query_price,
    query_trains,
    resolve_station_candidates,
)

# query result 的 '|' 分隔字段索引（已用 probe 脚本实测确认）
IDX_TRAIN_CODE = 3
IDX_START_TIME = 8
IDX_ARRIVE_TIME = 9
IDX_LISHI = 10          # 官方历时 "07:32"

HSR_RE = re.compile(r"^[GDC]")
MAX_MINUTES = 48 * 60   # 过滤 99:59 这类脏值

HERE = Path(__file__).resolve().parent
OUT = HERE / "captured" / "train_binding.json"


def lishi_to_minutes(v: str) -> Optional[int]:
    """'07:32' → 452"""
    m = re.match(r"^(\d{1,3}):(\d{2})$", (v or "").strip())
    if not m:
        return None
    return int(m.group(1)) * 60 + int(m.group(2))


def classify(code: str) -> str:
    return "高铁动车" if HSR_RE.match(code.upper()) else "普速"


def pick_representatives(rows: List[List[str]]) -> Dict[str, dict]:
    """在「高铁动车 / 普速」两类中各挑历时最短的一趟作为代表车次。

    取最快而不是最便宜，是为了让每一档的时长如实反映该档的实际体验：
    高铁档就该是 2 小时，普速档就该是 7 小时。价格由该车次自己决定。
    """
    best: Dict[str, dict] = {}
    for f in rows:
        if len(f) <= max(IDX_LISHI, IDX_SEAT_TYPES):
            continue
        code = (f[IDX_TRAIN_CODE] or "").strip()
        if not code:
            continue
        mins = lishi_to_minutes(f[IDX_LISHI])
        if not mins or mins <= 0 or mins > MAX_MINUTES:
            continue
        kind = classify(code)
        cur = best.get(kind)
        if cur is None or mins < cur["minutes"]:
            best[kind] = {
                "train_code": code,
                "depart": (f[IDX_START_TIME] or "").strip(),
                "arrive": (f[IDX_ARRIVE_TIME] or "").strip(),
                "lishi": (f[IDX_LISHI] or "").strip(),
                "minutes": mins,
                "_fields": f,
            }
    return best


def scrape_pair(s, a: str, b: str, codes: Dict[str, str], train_date: str,
                sleep: float) -> Optional[dict]:
    a_cands = resolve_station_candidates(a, codes)
    b_cands = resolve_station_candidates(b, codes)
    if not a_cands or not b_cands:
        return None

    rows: List[List[str]] = []
    last_err = "no_train"
    for a_code, _a_name in a_cands:
        for b_code, _b_name in b_cands:
            got = query_trains(s, a_code, b_code, train_date)
            if got and got[0] and got[0][0] == "_error":
                last_err = got[0][1] if len(got[0]) > 1 else "query_failed"
                continue
            if got:
                rows = got
                break
            last_err = "no_train"
        if rows:
            break

    if not rows:
        return {"_error": last_err} if last_err != "no_train" else {"train_count": 0}

    reps = pick_representatives(rows)
    out: Dict[str, dict] = {}
    for kind, rep in reps.items():
        prices = query_price(s, rep["_fields"], train_date)
        time.sleep(sleep + random.uniform(0, 0.4))
        item = {k: v for k, v in rep.items() if k != "_fields"}
        # 无座与某席别同价时保留，但「无座」不作为可推荐席别
        item["seats"] = {k: v for k, v in prices.items() if k != "无座"}
        if not item["seats"]:
            continue
        out[kind] = item

    if not out:
        return {"_error": "no_price"}
    out["_meta"] = {"train_count": len(rows), "date": train_date}
    return out


PRICE_TABLE = (HERE.parent.parent.parent / "ai-tourism" / "src" / "main" / "resources"
               / "price" / "train_price_local.json")


def load_existing_pairs() -> List[tuple]:
    """沿用旧票价表覆盖的城市对（378 对），保证新旧数据可逐条对比。"""
    if not PRICE_TABLE.exists():
        return []
    data = json.loads(PRICE_TABLE.read_text(encoding="utf-8"))
    pairs = []
    for key in data.keys():
        a, _, b = key.partition("-")
        if a and b:
            pairs.append((a, b))
    return pairs


def load_result() -> dict:
    if OUT.exists():
        return json.loads(OUT.read_text(encoding="utf-8"))
    return {}


def save_result(r: dict) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--pair", type=str, default="")
    ap.add_argument("--pending", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--sleep", type=float, default=1.2)
    ap.add_argument("--tier", type=int, default=None)
    args = ap.parse_args()

    result = load_result()

    pairs: List[tuple] = []
    if args.pair:
        a, b = [x.strip() for x in args.pair.split(",")]
        pairs = [(a, b)]
    else:
        # 只抓现有票价表已经覆盖的线路，保证两套数据可逐条对比、覆盖面不外扩
        pairs = load_existing_pairs()
        if args.tier is not None:
            cities = set(load_cities(args.tier))
            pairs = [p for p in pairs if p[0] in cities and p[1] in cities]
    if args.pending:
        pairs = [p for p in pairs if f"{p[0]}-{p[1]}" not in result]
    elif not args.force:
        pairs = [p for p in pairs if f"{p[0]}-{p[1]}" not in result]
    if args.limit:
        pairs = pairs[:args.limit]

    train_date = (time.strftime("%Y-%m-%d", time.localtime(time.time() + 10 * 86400)))
    print(f"[info] 待抓 {len(pairs)} 对，日期 {train_date}")

    s = new_session()
    codes = fetch_station_codes(s)
    print(f"[info] 站码 {len(codes)} 条")

    fails = 0
    for i, (a, b) in enumerate(pairs, 1):
        key = f"{a}-{b}"
        try:
            r = scrape_pair(s, a, b, codes, train_date, args.sleep)
        except Exception as e:  # noqa: BLE001
            r = {"_error": f"exception:{e}"}
        if r is None:
            r = {"_error": "no_station"}
        if "_error" in r:
            fails += 1
            print(f"  [{i}/{len(pairs)}] {key} 失败: {r['_error']}")
            if fails >= 8:
                print("[warn] 连续失败过多，疑似风控，提前退出")
                save_result(result)
                return
            # 网络/风控类错误不落盘，便于 --pending 重试；「真无车次」单独记一条
            if r["_error"] == "no_train":
                result[key] = {"train_count": 0}
        else:
            result[key] = r
            fails = 0
            kinds = {k: (v["train_code"], v["lishi"], list(v["seats"].items())[:2])
                     for k, v in r.items()
                     if isinstance(v, dict) and "train_code" in v}
            print(f"  [{i}/{len(pairs)}] {key} {kinds}")
        if i % 20 == 0:
            save_result(result)
        time.sleep(args.sleep + random.uniform(0, 0.6))

    save_result(result)
    ok = sum(1 for v in result.values() if "_error" not in v and v)
    print(f"\n[done] 成功 {ok} 条，写入 {OUT}")


if __name__ == "__main__":
    main()
