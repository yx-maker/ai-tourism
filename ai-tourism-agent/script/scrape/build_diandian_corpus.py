# -*- coding: utf-8 -*-
"""
把 captured/xhs_diandian.json（点点 AI 问答）转成 data.csv 行追加。
来源标记：url = xhs://diandian/{city}-{kind}（幂等去重键）
"""
import argparse
import csv
import json
from pathlib import Path

HERE = Path(__file__).parent
SRC = HERE / "captured" / "xhs_diandian.json"
DATA_CSV = HERE.parent / "data.csv"

HEADER = ["source_city", "url", "title", "time", "view_count", "comment_count",
          "favorite_count", "share_count", "support_count", "travel_days",
          "travel_people", "avg_cost", "text"]

KIND_TITLE = {"route": "小红书AI总结·一日游路线规划", "food": "小红书AI总结·特色美食推荐"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="实际写盘（默认预演）")
    args = ap.parse_args()

    data = json.loads(SRC.read_text(encoding="utf-8"))
    enc = "gb18030"  # data.csv 已知 GBK（同 build_xhs_corpus 探测结论）
    existing = set()
    with open(DATA_CSV, encoding=enc, newline="") as f:
        for row in csv.DictReader(f):
            existing.add(row.get("url", ""))
    print(f"data.csv 已有 {len(existing)} 行")

    new_rows = []
    for key, v in data.items():
        url = f"xhs://diandian/{key}"
        if url in existing:
            continue
        if v.get("chars", 0) < 300:
            print(f"[skip] {key}: {v.get('chars')} 字过短")
            continue
        kind = key.rsplit("-", 1)[-1]
        city = key[: -len(kind) - 1]
        new_rows.append({
            "source_city": city,
            "url": url,
            "title": f"{KIND_TITLE.get(kind, kind)}（{city}）",
            "time": "",
            "view_count": "",
            "comment_count": "",
            "favorite_count": "",
            "share_count": "",
            "support_count": "",
            "travel_days": "",
            "travel_people": "",
            "avg_cost": "",
            "text": v["answer"].strip(),
        })

    print(f"将追加 {len(new_rows)} 行")
    for r in new_rows[:2]:
        print("  样例:", r["title"], "|", len(r["text"]), "字")
    if not args.apply:
        print("（预演模式，加 --apply 写盘）")
        return

    with open(DATA_CSV, "a", encoding=enc, newline="") as f:
        w = csv.DictWriter(f, fieldnames=HEADER)
        for r in new_rows:
            w.writerow(r)
    print(f"✔ 已追加 {len(new_rows)} 行 → {DATA_CSV}")


if __name__ == "__main__":
    main()
