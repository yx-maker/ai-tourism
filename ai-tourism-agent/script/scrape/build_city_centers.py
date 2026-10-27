# -*- coding: utf-8 -*-
"""
生成全国城市中心坐标表（city_centers.json），供 Java 侧做「景点坐标是否串城市」校验。

背景：CityGeoUtil 只硬编码了 49 个城市的中心坐标，而景点库覆盖 389 个城市，
其余 340 城没有中心点，导致无法校验 LLM 给出的经纬度是否属于目标城市
（典型故障：银川行程里的「回民街」被写成西安回民街、福州行程里的「西湖公园」被写成杭州西湖）。

做法：用 t_poi 里各城市已有景点坐标取**中位数**作为城市中心。
中位数对少量跨城污染点（同名景点被误录）比平均值鲁棒。
"""
import json
import statistics
import subprocess
from collections import defaultdict
from pathlib import Path

MYSQL = r"C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe"
OUT = Path(r"C:\Users\28948\Desktop\毕业论文\ai-tourism\src\main\resources\city_centers.json")

# 中国经纬度合理范围（用于剔除明显错误/未填的坐标）
LNG_RANGE = (73.0, 136.0)
LAT_RANGE = (3.0, 54.0)


def q(sql):
    out = subprocess.run(
        [MYSQL, "-h", "127.0.0.1", "-u", "root", "-p123456", "aitourism",
         "--default-character-set=utf8mb4", "-N", "-B", "-e", sql],
        capture_output=True)
    return out.stdout.decode("utf-8", errors="replace")


def main():
    print("读取 t_poi 坐标…")
    rows = q("SELECT city_name, poi_longitude, poi_latitude FROM t_poi "
             "WHERE poi_longitude IS NOT NULL AND poi_latitude IS NOT NULL "
             "AND poi_longitude<>0 AND poi_latitude<>0;")
    buckets = defaultdict(lambda: {"lng": [], "lat": []})
    n = 0
    for line in rows.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        city = parts[0].strip()
        try:
            lng = float(parts[1])
            lat = float(parts[2])
        except ValueError:
            continue
        if not (LNG_RANGE[0] <= lng <= LNG_RANGE[1] and LAT_RANGE[0] <= lat <= LAT_RANGE[1]):
            continue
        buckets[city]["lng"].append(lng)
        buckets[city]["lat"].append(lat)
        n += 1
    print(f"有效坐标 {n} 条，覆盖 {len(buckets)} 个城市")

    centers = {}
    for city, v in buckets.items():
        if not v["lng"]:
            continue
        centers[city] = {
            "lng": round(statistics.median(v["lng"]), 4),
            "lat": round(statistics.median(v["lat"]), 4),
            "n": len(v["lng"]),
        }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps({"generated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
                    "source": "t_poi median",
                    "total": len(centers),
                    "centers": centers}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    print(f"已写入 {OUT}  城市数={len(centers)}")

    for c in ("银川", "福州", "西安", "杭州", "洛阳"):
        if c in centers:
            print(f"  {c}: {centers[c]}")


if __name__ == "__main__":
    main()
