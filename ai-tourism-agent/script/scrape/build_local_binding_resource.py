# -*- coding: utf-8 -*-
"""captured/train_binding.json → ai-tourism/src/main/resources/price/train_binding_local.json

同一趟车（train_code）同时携带「官方历时」与「该车各席别票价」，票价与时长永不跨车次错配。
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "captured" / "train_binding.json"
DST = HERE.parent.parent.parent / "ai-tourism" / "src" / "main" / "resources" / "price" / "train_binding_local.json"

MAX_MINUTES = 48 * 60
VALID_SEATS = {
    "高铁动车": {"二等座", "一等座", "商务座", "特等座", "无座"},
    "普速": {"硬座", "硬卧", "软卧", "软座", "高级软卧", "包厢硬卧"},
}
# 每档至少要有一个「可推荐」席别（无座不算）
MIN_USABLE = {"高铁动车": {"二等座", "一等座"}, "普速": {"硬座", "硬卧", "软卧", "软座"}}

# 12306 席别码别名：D 字头动集（CR200J）用 AI/AJ 表示一/二等座，
# 与 G 车的 M/O 是同一席别的两套编码，不翻译会让这些车次被整条丢弃。
SEAT_ALIAS = {
    "AI": "一等座",
    "AJ": "二等座",
    "P": "特等座",
    "MIN": "",          # 前端「¥xx 起」的展示码，不是真实席别
}


def main() -> None:
    data = json.loads(SRC.read_text(encoding="utf-8"))
    out: dict = {}
    skipped = []
    dropped_seat = []

    for pair, v in data.items():
        if not isinstance(v, dict) or "_error" in v or not v:
            skipped.append(pair)
            continue
        route = {}
        for kind in ("高铁动车", "普速"):
            item = v.get(kind)
            if not isinstance(item, dict):
                continue
            mins = item.get("minutes")
            if not isinstance(mins, int) or mins <= 0 or mins > MAX_MINUTES:
                continue
            seats = item.get("seats") or {}
            clean = {}
            for name, price in seats.items():
                name = SEAT_ALIAS.get(name, name)
                if not name:
                    continue
                if name not in VALID_SEATS[kind]:
                    dropped_seat.append(f"{pair}/{kind}={name}")
                    continue
                if not isinstance(price, (int, float)) or price <= 0:
                    continue
                clean[name] = round(float(price), 1)
            if not (set(clean) & MIN_USABLE[kind]):
                continue
            route[kind] = {
                "train_code": item.get("train_code"),
                "depart": item.get("depart"),
                "arrive": item.get("arrive"),
                "lishi": item.get("lishi"),
                "minutes": mins,
                "seats": clean,
            }
        if route:
            out[pair] = route
            # 反向也写一份（票价与时长对称，避免“只有正向能查”）
            a, _, b = pair.partition("-")
            rev = f"{b}-{a}"
            if rev not in out and f"{b}-{a}" not in data:
                out[rev] = route
        else:
            skipped.append(pair)

    DST.parent.mkdir(parents=True, exist_ok=True)
    DST.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    sf = sum(1 for v in out.values() if "高铁动车" in v)
    sl = sum(1 for v in out.values() if "普速" in v)
    print(f"线路 {len(out)} 条（含高铁动车 {sf}，含普速 {sl}）；跳过 {len(skipped)} 条")
    if dropped_seat:
        print(f"丢弃席别 {len(dropped_seat)} 个：{dropped_seat[:5]}")
    print(f"写入 {DST}")


if __name__ == "__main__":
    main()
