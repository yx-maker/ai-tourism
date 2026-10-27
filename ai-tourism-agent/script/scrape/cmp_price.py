# -*- coding: utf-8 -*-
"""对比：爬虫产出 captured/train_price.json 与 Java 使用的 train_price_local.json"""
import json
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]  # ai-tourism-agent
CAP = BASE / "script" / "scrape" / "captured" / "train_price.json"
JAVA = BASE.parent / "ai-tourism" / "src" / "main" / "resources" / "price" / "train_price_local.json"

cap = json.loads(CAP.read_text(encoding="utf-8"))
loc = json.loads(JAVA.read_text(encoding="utf-8"))
print("captured pairs:", len(cap))
print("java routes   :", len(loc))

for k in ["广州-西安", "西安-广州", "北京-上海"]:
    print("---", k)
    print("  CAP :", json.dumps(cap.get(k), ensure_ascii=False)[:220])
    print("  JAVA:", json.dumps(loc.get(k), ensure_ascii=False)[:220])

# 覆盖率：captured 里有价的对，java 里是否都有（正向 + 反向）
miss = []
for key, v in cap.items():
    if not isinstance(v, dict) or not v.get("min_price"):
        continue
    a, b = key.split("-", 1)
    for kk in (f"{a}-{b}", f"{b}-{a}"):
        if kk not in loc:
            miss.append(kk)
print("captured 有价但 java 缺失的路由数:", len(miss))
print("示例缺失:", miss[:10])
