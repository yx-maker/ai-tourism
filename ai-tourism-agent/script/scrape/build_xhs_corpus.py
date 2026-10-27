# -*- coding: utf-8 -*-
"""
把 captured/xhs_notes.json 转成 data.csv 行并追加（与马蜂窝语料同 14 列格式）。
列: source_city,url,title,time,view_count,comment_count,favorite_count,
    share_count,support_count,travel_days,travel_people,avg_cost,text

用法：
    python build_xhs_corpus.py            # 预演：打印将追加的样例行与统计
    python build_xhs_corpus.py --apply    # 实际追加到 ../data.csv（自动去重）
"""
import argparse
import csv
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
NOTES = HERE / "captured" / "xhs_notes.json"
DATA_CSV = HERE.parent / "data.csv"

HEADER = ["source_city", "url", "title", "time", "view_count", "comment_count",
          "favorite_count", "share_count", "support_count", "travel_days",
          "travel_people", "avg_cost", "text"]

_num_re = re.compile(r"([\d.]+)\s*([万wW]?)")


def parse_count(s: str) -> str:
    """小红书计数 '1.2万' → '12000'；空/'赞' → ''"""
    s = (s or "").strip()
    if not s:
        return ""
    m = _num_re.search(s)
    if not m:
        return ""
    v = float(m.group(1))
    if m.group(2):
        v *= 10000
    return str(int(v))


def clean_text(t: str) -> str:
    """去掉话题标签(#xx[话题]#)、@用户、emoji 密集段落不做处理（保留原文风味）"""
    t = re.sub(r"#[^#\n]{1,30}#\s*", "", t)          # #话题#
    t = re.sub(r"@[^\s\n]{2,20}", "", t)              # @用户
    t = re.sub(r"\[表情\]|\u200b", "", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="实际写库（默认预演）")
    args = ap.parse_args()

    notes = json.loads(NOTES.read_text(encoding="utf-8"))
    print(f"笔记源: {len(notes)} 篇")

    # 已存在的 url（幂等，重复运行不重复追加）
    # 沿用 data.csv 原编码（csv_loader 自动探测 gb18030/utf-8-sig，追加时必须同编码）
    enc = "utf-8-sig"
    if DATA_CSV.exists():
        head = DATA_CSV.open("rb").read(200)
        try:
            head.decode("utf-8-sig")
        except UnicodeDecodeError:
            enc = "gb18030"
    print(f"data.csv 编码: {enc}")

    existing = set()
    with open(DATA_CSV, encoding=enc, newline="") as f:
        for row in csv.DictReader(f):
            existing.add(row.get("url", ""))
    print(f"data.csv 已有 {len(existing)} 行")

    new_rows = []
    for n in notes:
        if n["url"] in existing:
            continue
        text = clean_text(n["text"])
        if len(text) < 50:
            continue
        new_rows.append({
            "source_city": n["city"],
            "url": n["url"],
            "title": n["title"].strip()[:100],
            "time": n.get("date", ""),
            "view_count": "",
            "comment_count": parse_count(n.get("comments", "")),
            "favorite_count": parse_count(n.get("collects", "")),
            "share_count": "",
            "support_count": parse_count(n.get("likes", "")),
            "travel_days": "",
            "travel_people": "",
            "avg_cost": "",
            "text": text,
        })

    print(f"将追加 {len(new_rows)} 行")
    if new_rows:
        r = new_rows[0]
        print("样例:", r["source_city"], "|", r["title"][:30], "| 正文", len(r["text"]), "字 | 赞", r["support_count"])

    if not args.apply:
        print("\n（预演模式，未写盘。加 --apply 实际追加）")
        return

    file_empty = not DATA_CSV.exists() or DATA_CSV.stat().st_size == 0
    with open(DATA_CSV, "a", encoding=enc, newline="") as f:
        w = csv.DictWriter(f, fieldnames=HEADER)
        if file_empty:
            w.writeheader()
        for r in new_rows:
            w.writerow(r)
    print(f"✔ 已追加 {len(new_rows)} 行 → {DATA_CSV}")


if __name__ == "__main__":
    main()
