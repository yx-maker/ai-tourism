# -*- coding: utf-8 -*-
"""
清洗历史会话 daily_routes 中的「串城市」坐标。

问题：大模型生成路线时自带经纬度，但常按同名景点最出名的地点给坐标——
银川行程的「回民街」被写成西安回民街(108.9,34.3)、
福州行程的「西湖公园」被写成杭州西湖(120.15,30.25)，
整条路线因此被画到别的省。

处理：对每个点位，若其坐标偏离所属城市中心超过阈值，就视为串城市，
优先用景点库 (city_name + poi_name) 的真实坐标替换，否则回退到城市中心。

用法：
    python fix_daily_routes_coords.py           # 预演，只打印不写库
    python fix_daily_routes_coords.py --apply   # 实际写库
"""
import json
import math
import subprocess
import sys
from pathlib import Path

MYSQL = r"C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe"
CENTERS = Path(r"C:\Users\28948\Desktop\毕业论文\ai-tourism\src\main\resources\city_centers.json")
MAX_KM = 80.0


def q(sql):
    out = subprocess.run(
        [MYSQL, "-h", "127.0.0.1", "-u", "root", "-p123456", "aitourism",
         "--default-character-set=utf8mb4", "-N", "-B", "-e", sql],
        capture_output=True)
    return out.stdout.decode("utf-8", errors="replace")


def esc(s):
    return str(s).replace("\\", "\\\\").replace("'", "''")


def haversine(lat1, lon1, lat2, lon2):
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def in_china(lng, lat):
    return 73.0 <= lng <= 136.0 and 3.0 <= lat <= 54.0


def main():
    apply = "--apply" in sys.argv
    centers = json.load(open(CENTERS, encoding="utf-8"))["centers"]
    print(f"已载入城市中心 {len(centers)} 城，阈值 {MAX_KM}km，模式={'写库' if apply else '预演'}")

    # 景点库索引：(city, name) -> (lng, lat)，以及 city -> [(name,lng,lat)] 供包含匹配
    print("读取景点库坐标…")
    poi_exact = {}
    poi_by_city = {}
    rows = q("SELECT city_name, poi_name, poi_longitude, poi_latitude FROM t_poi "
             "WHERE poi_longitude<>0 AND poi_latitude<>0;")
    for line in rows.splitlines():
        p = line.split("\t")
        if len(p) < 4:
            continue
        city, name = p[0].strip(), p[1].strip()
        try:
            lng, lat = float(p[2]), float(p[3])
        except ValueError:
            continue
        if not in_china(lng, lat):
            continue
        poi_exact[(city, name)] = (lng, lat)
        poi_by_city.setdefault(city, []).append((name, lng, lat))
    print(f"景点库 {len(poi_exact)} 条")

    print("读取会话路线…")
    rows = q("SELECT session_id, daily_routes FROM t_ai_assistant_sessions "
             "WHERE daily_routes IS NOT NULL AND daily_routes<>'';")
    sessions = []
    for line in rows.splitlines():
        if "\t" not in line:
            continue
        sid, raw = line.split("\t", 1)
        sessions.append((sid.strip(), raw))
    print(f"共 {len(sessions)} 个会话")

    total_fixed = 0
    for sid, raw in sessions:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        changed = False
        for day in data.get("dailyRoutes", []) or []:
            for pt in day.get("points", []) or []:
                city = (pt.get("city") or "").strip()
                name = (pt.get("keyword") or "").strip()
                lng, lat = pt.get("longitude"), pt.get("latitude")
                if lng is None or lat is None or not city:
                    continue
                try:
                    lng, lat = float(lng), float(lat)
                except (TypeError, ValueError):
                    continue

                bad = (not in_china(lng, lat)) or (
                    city in centers and haversine(centers[city]["lat"], centers[city]["lng"], lat, lng) > MAX_KM)
                if not bad:
                    continue

                # 串城市：优先用景点库真实坐标（精确 → 城市内包含匹配）
                new = poi_exact.get((city, name))
                if new is None:
                    for pn, plng, plat in poi_by_city.get(city, []):
                        if name and (name in pn or pn in name):
                            new = (plng, plat)
                            break
                if new is None and city in centers:
                    new = (centers[city]["lng"], centers[city]["lat"])

                if new is None:
                    print(f"  [{sid[:8]}] {city}「{name}」串城但无处可换，原 ({lng},{lat})")
                    continue
                dist = haversine(centers[city]["lat"], centers[city]["lng"], lat, lng) if city in centers else -1
                print(f"  [{sid[:8]}] {city}「{name}」({lng},{lat}) 距市中心 {dist:.0f}km → ({new[0]},{new[1]})")
                pt["longitude"], pt["latitude"] = new[0], new[1]
                changed = True
                total_fixed += 1

        if changed and apply:
            out = json.dumps(data, ensure_ascii=False)
            q(f"UPDATE t_ai_assistant_sessions SET daily_routes='{esc(out)}' "
              f"WHERE session_id='{esc(sid)}';")

    print(f"\n修正点位 {total_fixed} 个" + ("（已写库）" if apply else "（预演未写库，加 --apply 生效）"))


if __name__ == "__main__":
    main()
