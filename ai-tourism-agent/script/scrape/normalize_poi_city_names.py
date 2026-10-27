# -*- coding: utf-8 -*-
"""
把 t_poi 里的城市名归并为 cities_cn.json 的规范名。

为什么需要：
    景点补录早期用行政区划全名入库，产生「红河哈尼族」「南投县」「湘西土家族」
    这类半吊子城市名；而用户/模型查询时用的是通用名「红河」「南投」「湘西」，
    导致明明有数据却检索不到（实测 `/api/tools/poi?city_name=红河` 返回 0 条）。
    同一城市还可能因新旧名并存而出现两套记录。

做法：
    1. 以 cities_cn.json 的规范名为准；
    2. DB 中不在规范集里的城市名，用 build_city_list.strip_suffix 归一化后再匹配；
    3. UPDATE 改名，随后按 (city_name, poi_name) 去重，保留 id 最小的一条。

用法：
    python normalize_poi_city_names.py            # 预览将要做的改名
    python normalize_poi_city_names.py --apply    # 实际执行
"""
import argparse
import json
import sys
from pathlib import Path

import pymysql

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from build_city_list import strip_suffix  # noqa: E402

CITY_LIST_FILE = HERE / "cities_cn.json"
DB = dict(host="127.0.0.1", port=3306, user="root", password="123456",
          database="aitourism", charset="utf8mb4")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="实际执行改名与去重（默认预览）")
    args = ap.parse_args()

    if not CITY_LIST_FILE.exists():
        print("[error] 缺少 cities_cn.json，请先运行 build_city_list.py", file=sys.stderr)
        sys.exit(1)
    canon = {c["name"] for c in
             (json.loads(CITY_LIST_FILE.read_text(encoding="utf-8")).get("cities") or [])}

    conn = pymysql.connect(**DB)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT city_name FROM t_poi")
            db_cities = [r[0] for r in cur.fetchall()]

        mapping = {}
        for name in db_cities:
            if name in canon:
                continue
            fixed = strip_suffix(name)
            if fixed in canon:
                mapping[name] = fixed
            elif fixed and fixed != name:
                # 规范清单里也没有，但归一化后更通用，仍然改名
                mapping[name] = fixed

        print(f"规范城市 {len(canon)} 个；库内城市 {len(db_cities)} 个；待归并 {len(mapping)} 个")
        for old, new in sorted(mapping.items()):
            print(f"  {old} → {new}")
        if not mapping:
            print("无需归并")
            return
        if not args.apply:
            print("\n[预览模式] 加 --apply 才会执行")
            return

        with conn.cursor() as cur:
            for old, new in mapping.items():
                cur.execute("UPDATE t_poi SET city_name=%s WHERE city_name=%s", (new, old))
            conn.commit()
            print(f"\n已改名 {len(mapping)} 个城市")

            # 去重：同城市同景点保留 id 最小的一条
            cur.execute("""
                DELETE p FROM t_poi p
                JOIN (SELECT city_name, poi_name, MIN(id) keep_id
                      FROM t_poi GROUP BY city_name, poi_name
                      HAVING COUNT(*)>1) d
                  ON p.city_name=d.city_name AND p.poi_name=d.poi_name
                 WHERE p.id > d.keep_id
            """)
            removed = cur.rowcount
            conn.commit()
            print(f"已去重 {removed} 条重复记录")

            cur.execute("SELECT COUNT(*), COUNT(DISTINCT city_name) FROM t_poi")
            n, city = cur.fetchone()
            print(f"当前景点库：{n} 条 / {city} 城")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
