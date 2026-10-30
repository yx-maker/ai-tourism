# -*- coding: utf-8 -*-
"""12306 车次「历时」抓取（纯 HTTP，不查价）—— 给预算系统提供真实交通时长。

为什么要单独做这个脚本
    票价表（train_price_local.json）只有价格，没有耗时。预算系统要回答
    「这趟大交通要坐多久」，同样必须优先用真实数据，而不是凭感觉估算。

    12306 的车次查询接口（/otn/leftTicket/query）返回的每条记录里，
    索引 10 就是官方历时（lishi，格式 "07:32"），索引 3 是车次号（G2942）。
    这意味着**不需要浏览器、不需要查价接口**，一对城市只要 1 个请求就能拿到
    全部车次的真实历时，成本远低于票价抓取。

    按车次类型分两类保存（与预算选交通方式的口径对应）：
        高铁动车 = G/D/C 开头
        普速列车 = Z/T/K/Y/P/S 或纯数字（绿皮、直快、特快）
    每类取**最快的一趟**（用户关心的是理想耗时），同时保留车次号与到发时间，
    使前端可以展示「G2942 07:44→14:46 约 7 小时 2 分」，来源可追溯。

用法：
    python fetch_train_duration_http.py --limit 12        # 试跑前 12 对
    python fetch_train_duration_http.py                   # 全量（票价表已覆盖的线路，约 378 对）
    python fetch_train_duration_harp.py --pair 广州 成都   # 单对补抓
    python fetch_train_duration_http.py --pending         # 补抓预算系统累积的缺失城市对
    python fetch_train_duration_http.py --force           # 忽略缓存重抓

输出：captured/train_duration.json（供 build_local_duration_resource.py 生成 Java 资源）
"""
import argparse
import json
import random
import re
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from fetch_train_price_http import (  # noqa: E402
    new_session, fetch_station_codes, resolve_station_candidates, query_trains)

OUT_FILE = HERE / "captured" / "train_duration.json"
PENDING_FILE = HERE / "pending_pairs.json"
PRICE_RESOURCE = Path(
    r"C:\Users\28948\Desktop\毕业论文\ai-tourism\src\main\resources\price\train_price_local.json")

# query result 字段索引（与 fetch_train_price_http 同一套）
IDX_TRAIN_CODE = 3
IDX_START_TIME = 8
IDX_ARRIVE_TIME = 9
IDX_LISHI = 10

# 12306 预售期约 15 天：取「今天 + 10 天」保证有车次
QUERY_DATE = (date.today() + timedelta(days=10)).isoformat()

HSR_RE = re.compile(r"^[GDC]", re.I)  # 高铁 / 动车 / 城际

# 12306 偶发脏数据：个别车次历时显示 99:59（如 Z168 广州-济南），
# 明显超出国内铁路实际可达范围，按 48 小时封顶过滤，避免污染时长表。
MAX_MINUTES = 48 * 60


def load_result() -> dict:
    if OUT_FILE.exists():
        try:
            return json.loads(OUT_FILE.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}
    return {}


def save_result(r: dict):
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(OUT_FILE)


def lishi_to_minutes(v: str) -> Optional[int]:
    """'07:32' → 452；跨天也支持（'23:35' → 1415）"""
    if not v:
        return None
    m = re.match(r"^(\d{1,3}):(\d{2})$", v.strip())
    if not m:
        return None
    return int(m.group(1)) * 60 + int(m.group(2))


def classify(code: str) -> str:
    """车次号 → 类型标签：高铁动车 / 普速"""
    c = (code or "").strip().upper()
    if HSR_RE.match(c):
        return "高铁动车"
    return "普速"


def best_of(rows: List[List[str]]) -> Dict[str, dict]:
    """从车次列表里挑出每类的最快一趟（只保留可解析历时的车次）"""
    best: Dict[str, dict] = {}
    for f in rows:
        if len(f) <= IDX_LISHI:
            continue
        code = f[IDX_TRAIN_CODE]
        mins = lishi_to_minutes(f[IDX_LISHI])
        if not code or not mins or mins > MAX_MINUTES:
            continue
        kind = classify(code)
        cur = best.get(kind)
        if cur is None or mins < cur["minutes"]:
            best[kind] = {
                "train_code": code,
                "depart": f[IDX_START_TIME],
                "arrive": f[IDX_ARRIVE_TIME],
                "lishi": f[IDX_LISHI],
                "minutes": mins,
            }
    return best


def scrape_pair(s, a: str, b: str, codes: Dict[str, str]) -> Optional[dict]:
    """抓一对城市的两类最快历时；返回 None 表示站码缺失"""
    a_cands = resolve_station_candidates(a, codes)
    b_cands = resolve_station_candidates(b, codes)
    if not a_cands or not b_cands:
        return None

    rows: List[List[str]] = []
    last_err = "no_train"
    for (a_code, _an) in a_cands[:3]:          # 最多试 3 个候选站（广州 / 广州南 / 广州东…）
        for (b_code, _bn) in b_cands[:3]:
            got = query_trains(s, a_code, b_code, QUERY_DATE)
            if got and got[0] and got[0][0] == "_error":
                last_err = got[0][1] if len(got[0]) > 1 else "query_failed"
                time.sleep(random.uniform(2.0, 3.5))
                continue
            if got:
                rows = got
                break
            last_err = "no_train"
        if rows:
            break
    if not rows:
        # 区分「真无直通车」与「被风控」：被风控的记录下来，下一轮可重试
        return {"_error": last_err} if last_err != "no_train" else {
            "date": QUERY_DATE, "train_count": 0}

    best = best_of(rows)
    return {
        "date": QUERY_DATE,
        "train_count": len(rows),
        "types": best,
    }


def pairs_from_price_table() -> List[Tuple[str, str]]:
    """以票价表已覆盖的线路为准（预算真正会用到的城市对，约 378 条）"""
    if not PRICE_RESOURCE.exists():
        print(f"[warn] 票价表不存在：{PRICE_RESOURCE}", file=sys.stderr)
        return []
    data = json.loads(PRICE_RESOURCE.read_text(encoding="utf-8"))
    pairs = []
    for key in data:
        if "-" not in key:
            continue
        a, b = key.split("-", 1)
        if a and b:
            pairs.append((a, b))
    return pairs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 对（0=全量）")
    ap.add_argument("--pair", nargs=2, metavar=("FROM", "TO"), help="按需补抓单对")
    ap.add_argument("--pending", action="store_true", help="补抓 pending_pairs.json 的缺失城市对")
    ap.add_argument("--force", action="store_true", help="忽略缓存强制重抓")
    ap.add_argument("--sleep", type=float, default=1.2, help="每对间隔秒（默认 1.2，防风控）")
    args = ap.parse_args()

    if args.pair:
        pairs = [(args.pair[0], args.pair[1])]
    elif args.pending:
        if not PENDING_FILE.exists():
            print("[info] 无待抓城市对")
            return
        pend = json.loads(PENDING_FILE.read_text(encoding="utf-8"))
        pairs = [tuple(k.split("-", 1)) for k in (pend.get("pairs") or []) if "-" in k]
    else:
        pairs = pairs_from_price_table()
    if args.limit:
        pairs = pairs[: args.limit]
    if not pairs:
        print("[info] 没有待抓的城市对")
        return

    result = load_result()
    todo = [p for p in pairs
            if args.force or f"{p[0]}-{p[1]}" not in result
            or result[f"{p[0]}-{p[1]}"].get("_error")]
    print(f"共 {len(pairs)} 对，已缓存 {len(result)} 对，本轮待抓 {len(todo)} 对"
          f"（查询日期 {QUERY_DATE}）")
    if not todo:
        return

    s = new_session()
    codes = fetch_station_codes(s)
    done = 0
    err_streak = 0
    t0 = datetime.now()
    for a, b in todo:
        key = f"{a}-{b}"
        got = scrape_pair(s, a, b, codes)
        result[key] = got if got else {"_error": "station_missing"}
        done += 1
        if got and got.get("_error"):
            err_streak += 1
            print(f"[{done}/{len(todo)}] {key} 失败: {got['_error']}")
        else:
            err_streak = 0
            kinds = got.get("types") if got else None
            desc = "，".join(f"{k} {v['train_code']} {v['lishi']}"
                             for k, v in (kinds or {}).items()) or "无直通车"
            print(f"[{done}/{len(todo)}] {key} {got.get('train_count', 0)}趟 → {desc}")
        if done % 20 == 0:
            save_result(result)
        # 连续 8 次失败基本可以判定被风控，停手保住已有成果
        if err_streak >= 8:
            print(f"[warn] 连续 {err_streak} 次失败，疑似风控，提前结束（已抓 {done} 对）")
            break
        time.sleep(args.sleep + random.uniform(0, 0.6))

    save_result(result)
    ok = sum(1 for v in result.values() if not v.get("_error") and v.get("types"))
    print(f"===== 完成：{len(result)} 条记录，其中 {ok} 条有真实车次历时"
          f"（用时 {(datetime.now() - t0).total_seconds():.0f}s） =====")


if __name__ == "__main__":
    main()
