# -*- coding: utf-8 -*-
"""扫描 Java 票价表 train_price_local.json 中的席别 key 是否规范。
不规范（含空格/标点/异常字符）会导致按席别查价 miss → 退化到错误席别或估算，价格不准。
"""
import json
import re
from collections import Counter
from pathlib import Path

JAVA = Path(__file__).resolve().parents[2].parent / "ai-tourism" / "src" / "main" / "resources" / "price" / "train_price_local.json"
loc = json.loads(JAVA.read_text(encoding="utf-8"))

VALID = {"商务座", "特等座", "一等座", "二等座", "软卧", "硬卧", "软座", "硬座", "无座"}
bad = Counter()
bad_routes = {}

for route, seats in loc.items():
    if not isinstance(seats, dict):
        continue
    for k in seats.keys():
        if k not in VALID:
            bad[k] += 1
            bad_routes.setdefault(route, []).append(k)

print("总路由:", len(loc))
print("异常席别 key 种类:", len(bad))
for k, c in bad.most_common(30):
    print(f"  {k!r} 出现 {c} 次")
print("受影响路由数:", len(bad_routes))
for r, ks in list(bad_routes.items())[:10]:
    print("  ", r, ks)
