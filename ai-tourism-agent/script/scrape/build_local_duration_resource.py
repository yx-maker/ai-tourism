# -*- coding: utf-8 -*-
"""把 captured/train_duration.json（12306 实爬车次历时）转成 Java 资源文件：
ai-tourism/src/main/resources/price/train_duration_local.json

格式（与 train_price_local.json 同一套「城市A-城市B」key，双向保留）：
    {"北京-上海": {"高铁动车": {"train_code": "G25", "depart": "04:18",
                              "arrive": "08:36", "lishi": "04:18", "minutes": 258},
                  "普速":    {...}}}

只保留能解析出 minutes 的记录；无直通车的线路不写入（由预算引擎降级为速度模型估算）。
"""
import json
from pathlib import Path

HERE = Path(__file__).parent
SRC = HERE / "captured" / "train_duration.json"
DST = Path(
    r"C:\Users\28948\Desktop\毕业论文\ai-tourism\src\main\resources\price\train_duration_local.json")


def main():
    if not SRC.exists():
        print(f"[error] 抓取结果不存在：{SRC}\n"
              f"        请先运行：python fetch_train_duration_http.py", file=sys.stderr)
        return
    data = json.loads(SRC.read_text(encoding="utf-8"))
    out = {}
    skipped = 0
    dropped: list = []
    for key, v in data.items():
        if not isinstance(v, dict) or v.get("_error"):
            skipped += 1
            continue
        types = v.get("types") or {}
        cleaned = {}
        for kind, q in types.items():
            if not isinstance(q, dict) or not q.get("minutes"):
                continue
            # 12306 偶发脏数据（如 99:59）：超过 48 小时的一律丢弃，
            # 宁可让该线路降级为速度模型估算，也不能把荒谬值写进正式数据表。
            if int(q["minutes"]) > 48 * 60:
                dropped.append(f"{key}/{kind}={q['lishi']}")
                continue
            cleaned[kind] = {
                "train_code": q.get("train_code"),
                "depart": q.get("depart"),
                "arrive": q.get("arrive"),
                "lishi": q.get("lishi"),
                "minutes": int(q["minutes"]),
            }
        if cleaned:
            out[key] = cleaned
        else:
            skipped += 1

    DST.parent.mkdir(parents=True, exist_ok=True)
    DST.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    with_hsr = sum(1 for v in out.values() if "高铁动车" in v)
    with_normal = sum(1 for v in out.values() if "普速" in v)
    print(f"写入 {DST}")
    print(f"  线路 {len(out)} 条（跳过 {skipped} 条无车次/失败）"
          f"；含高铁动车 {with_hsr} 条，含普速 {with_normal} 条")
    if dropped:
        print(f"  丢弃异常历时 {len(dropped)} 条（>48h）：{dropped[:6]}")


if __name__ == "__main__":
    import sys
    main()
