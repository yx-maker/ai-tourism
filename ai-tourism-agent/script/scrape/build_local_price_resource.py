# -*- coding: utf-8 -*-
"""
把 captured/train_price.json（12306 实爬）转成 Java 资源文件：
ai-tourism/src/main/resources/price/train_price_local.json
格式 {"城市A-城市B": {"二等座": 338, ...}}，含双向 key，清洗席别名。
"""
import json
from pathlib import Path

HERE = Path(__file__).parent
SRC = HERE / "captured" / "train_price.json"
DST = Path(r"C:\Users\28948\Desktop\毕业论文\ai-tourism\src\main\resources\price\train_price_local.json")

SEAT_ORDER = ["二等座", "硬座", "无座", "硬卧", "软座", "软卧", "一等座", "特等座", "商务座", "高级软卧"]


def main():
    data = json.loads(SRC.read_text(encoding="utf-8"))
    out = {}
    skipped = []
    for key, v in data.items():
        if v.get("_error") or not v.get("min_price"):
            if v.get("_error"):
                skipped.append(key)
            continue
        # 清洗席别名（早期版本残留 "，商务座" / "车，硬座" 前缀）
        seats = {}
        for seat, price in v["min_price"].items():
            seat = seat.replace("，", "").replace("车", "") if "，" in seat else seat
            if seat in SEAT_ORDER and price > 0:
                # 同席别取更低价
                if seat not in seats or price < seats[seat]:
                    seats[seat] = price
        if not seats:
            skipped.append(key)
            continue
        ordered = {s: seats[s] for s in SEAT_ORDER if s in seats}
        out[key] = ordered

    # 双向 key（票价方向对称）
    bidirectional = {}
    for key, seats in out.items():
        a, _, b = key.partition("-")
        bidirectional[f"{a}-{b}"] = seats
        bidirectional[f"{b}-{a}"] = seats

    DST.parent.mkdir(parents=True, exist_ok=True)
    DST.write_text(json.dumps(bidirectional, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"线路 {len(out)} 对（双向 {len(bidirectional)} 键）→ {DST}")
    if skipped:
        print("跳过:", skipped)
    # 样例
    k = next(iter(out))
    print("样例:", k, out[k])


if __name__ == "__main__":
    main()
