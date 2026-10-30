# -*- coding: utf-8 -*-
"""探针：确认 12306 leftTicket/query 返回字段里「历时」的索引与格式。

只跑一对城市，打印前 3 趟车的车次号/出发/到达/历时候选字段，不写任何文件。
"""
import sys
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from fetch_train_price_http import (  # noqa: E402
    new_session, fetch_station_codes, resolve_station_candidates, query_trains)

TRAIN_DATE = (date.today() + timedelta(days=10)).isoformat()


def main():
    s = new_session()
    codes = fetch_station_codes(s)
    print("站码表条数:", len(codes))
    a = resolve_station_candidates("广州", codes)[0]
    b = resolve_station_candidates("成都", codes)[0]
    print("出发站:", a, "到达站:", b, "日期:", TRAIN_DATE)
    rows = query_trains(s, a[0], b[0], TRAIN_DATE)
    print("车次行数:", len(rows))
    if not rows:
        print("无车次（可能被风控或日期问题）")
        return
    f = rows[0]
    print("字段数:", len(f))
    for i, v in enumerate(f[:20]):
        print(f"  [{i}] {v!r}")
    print("--- 前 5 趟：车次/出发/到达/索引10/索引11 ---")
    for f in rows[:5]:
        if len(f) < 12:
            continue
        print(f"{f[3]:>8} | start={f[8]:>6} arrive={f[9]:>6} | [10]={f[10]!r} | [11]={f[11]!r}")


if __name__ == "__main__":
    main()
