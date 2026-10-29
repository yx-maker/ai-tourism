# -*- coding: utf-8 -*-
"""
生成「全国城市爬取表」——所有爬虫脚本共用的城市清单。

数据源：高德行政区划 API（v3/config/district），一次拉取 34 个省级 → 全部地级行政区。
用 adcode（行政区划代码）而非名称作为主键，避免「同名城市 / 民族自治州」歧义；
POI 与票价抓取均优先传 adcode，名称只用于展示与人工核对。

输出：script/scrape/cities_cn.json
    {
      "generated_at": "2026-10-26T...",
      "source": "amap-district-v3",
      "total": 337,
      "tier1": 62,                     # 省会 / 直辖市 / 计划单列市 / 热门旅游城市
      "cities": [
        {"name":"洛阳","full":"洛阳市","adcode":"410300","province":"河南省","tier":2},
        ...
      ]
    }

用法：
    python build_city_list.py              # 联网拉取并写入 cities_cn.json
    python build_city_list.py --print 20   # 只打印前 20 条，不落盘
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import requests

HERE = Path(__file__).parent
OUT_FILE = HERE / "cities_cn.json"
DISTRICT_URL = "https://restapi.amap.com/v3/config/district"

# 省会 / 自治区首府（不含直辖市，直辖市单独处理）
PROVINCE_CAPITALS = {
    "河北省": "石家庄", "山西省": "太原", "辽宁省": "沈阳", "吉林省": "长春",
    "黑龙江省": "哈尔滨", "江苏省": "南京", "浙江省": "杭州", "安徽省": "合肥",
    "福建省": "福州", "江西省": "南昌", "山东省": "济南", "河南省": "郑州",
    "湖北省": "武汉", "湖南省": "长沙", "广东省": "广州", "海南省": "海口",
    "四川省": "成都", "贵州省": "贵阳", "云南省": "昆明", "陕西省": "西安",
    "甘肃省": "兰州", "青海省": "西宁", "台湾省": "台北",
    "内蒙古自治区": "呼和浩特", "广西壮族自治区": "南宁", "西藏自治区": "拉萨",
    "宁夏回族自治区": "银川", "新疆维吾尔自治区": "乌鲁木齐",
    "香港特别行政区": "香港", "澳门特别行政区": "澳门",
}

# 直辖市（省级，无地级层级，需单独补进清单）
MUNICIPALITIES = {"北京市": "北京", "上海市": "上海", "天津市": "天津", "重庆市": "重庆",
                  "香港特别行政区": "香港", "澳门特别行政区": "澳门"}

# 计划单列市 + 高频旅游城市（票价组合优先覆盖，避免 O(n²) 爆炸）
HOT_TOURISM_CITIES = [
    "深圳", "厦门", "青岛", "大连", "宁波", "三亚", "桂林", "丽江", "张家界",
    "苏州", "无锡", "珠海", "汕头", "秦皇岛", "承德", "洛阳", "开封", "泰安",
    "黄山", "武夷山", "烟台", "威海", "扬州", "镇江", "绍兴", "嘉兴", "湖州",
    "常州", "温州", "泉州", "漳州", "惠州", "湛江", "北海", "大理", "西双版纳",
    "喀什", "拉萨", "日喀则", "敦煌", "嘉峪关", "张掖", "西宁", "银川", "呼和浩特",
    "哈尔滨", "长白山", "延吉", "丹东", "鞍山", "吉林", "大同", "平遥", "运城",
    "遵义", "安顺", "凯里", "腾冲", "香格里拉", "井冈山", "九江", "赣州",
]

# 地级行政区后缀 → 清洗为通用城市名
SUFFIXES = ["市", "自治州", "地区", "盟", "特别行政区", "自治区", "县"]


def get_amap_key() -> str:
    """从环境变量或 ai-tourism/.env.local 读取「Web服务」Key（不硬编码）。"""
    from amap_env import get_amap_web_key
    return get_amap_web_key()


# 民族修饰词：自治州全名里夹在中间的成分，需逐个剥离
# 「红河哈尼族彝族自治州」要剥掉「彝族」「哈尼族」两层才得到「红河」
ETHNIC = ["柯尔克孜族", "塔吉克族", "哈萨克族", "乌孜别克族", "土家族", "布依族",
          "傈僳族", "纳西族", "景颇族", "朝鲜族", "哈尼族", "蒙古族", "藏族",
          "回族", "羌族", "傣族", "彝族", "白族", "侗族", "苗族", "壮族",
          "瑶族", "黎族", "畲族", "满族", "土族", "撒拉族", "裕固族", "门巴族",
          "珞巴族", "基诺族", "德昂族", "阿昌族", "普米族", "怒族", "独龙族",
          # 不带「族」字结尾的变体：剥掉「自治州」后残留（如 伊犁哈萨克 → 伊犁）
          "哈萨克", "维吾尔", "塔吉克", "乌孜别克", "柯尔克孜", "东乡", "保安",
          "锡伯", "达斡尔", "鄂温克", "鄂伦春", "赫哲", "拉祜", "佤族", "布朗",
          "毛南", "仡佬"]


def strip_suffix(full: str) -> str:
    """行政区划全名 → 通用城市名。

    洛阳市→洛阳；延边朝鲜族自治州→延边；兴安盟→兴安；南投县→南投；
    红河哈尼族彝族自治州→红河（需连续剥离两个民族词）。
    """
    name = full
    # 1) 先剥行政区划后缀：延边朝鲜族自治州 → 延边朝鲜族
    for suf in ["自治州", "自治县", "地区", "盟", "特别行政区", "自治区"]:
        if name.endswith(suf) and len(name) > len(suf):
            name = name[: -len(suf)]
            break
    # 2) 再反复剥离民族修饰词（可能有多个）：红河哈尼族彝族 → 红河
    changed = True
    while changed:
        changed = False
        for eth in ETHNIC:
            if name.endswith(eth) and len(name) > len(eth):
                name = name[: -len(eth)]
                changed = True
    # 3) 收尾去掉 市 / 县
    for suf in ["市", "县"]:
        if name.endswith(suf) and len(name) > len(suf):
            name = name[: -len(suf)]
            break
    return name


def fetch_cities() -> List[Dict]:
    """拉取全国地级行政区（含直辖市）"""
    key = get_amap_key()

    def get(params):
        r = requests.get(DISTRICT_URL, params=params, timeout=25)
        d = r.json()
        if str(d.get("status")) != "1":
            print(f"[warn] district API: {d.get('info')}")
            return []
        return d.get("districts") or []

    roots = get({"key": key, "keywords": "中国", "subdistrict": 1,
                 "extensions": "base", "level": "country"})
    if not roots:
        print("[error] 未取到省级列表", file=sys.stderr)
        sys.exit(1)
    # country 查询会返回 1 个根（中华人民共和国），其 districts 才是 34 个省级
    provinces = roots
    if len(roots) == 1 and roots[0].get("districts"):
        provinces = roots[0]["districts"]

    cities: List[Dict] = []
    hot = set(HOT_TOURISM_CITIES)

    for prov in provinces:
        pname = prov.get("name") or ""
        padcode = prov.get("adcode") or ""

        # 直辖市：本身就是城市
        if pname in MUNICIPALITIES:
            cities.append({
                "name": MUNICIPALITIES[pname], "full": pname,
                "adcode": padcode, "province": pname, "tier": 1,
            })
            continue

        subs = get({"key": key, "keywords": padcode, "subdistrict": 1,
                    "extensions": "base"})
        if not subs:
            # 省级下钻失败，退化为 keywords=省名
            subs = get({"key": key, "keywords": pname, "subdistrict": 1,
                        "extensions": "base"})
        added = 0
        for s in subs:
            subs2 = s.get("districts") or []
            for c in subs2:
                full = (c.get("name") or "").strip()
                adcode = c.get("adcode") or ""
                if not full or not adcode:
                    continue
                # 香港 / 澳门 下辖只有 district（区），不是城市，跳过——省本身会单独补
                if c.get("level") == "district":
                    continue
                name = strip_suffix(full)
                capital = PROVINCE_CAPITALS.get(pname, "")
                tier = 1 if (name == capital or name in hot) else 2
                cities.append({
                    "name": name, "full": full, "adcode": adcode,
                    "province": pname, "tier": tier,
                })
                added += 1
        print(f"  {pname}: {added} 个城市")

    # 去重（按 adcode），保持省级顺序
    seen, uniq = set(), []
    for c in cities:
        if c["adcode"] in seen:
            continue
        seen.add(c["adcode"])
        uniq.append(c)
    return uniq


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--print", type=int, default=0, help="只打印前 N 条，不落盘")
    args = ap.parse_args()

    print("拉取全国行政区划（34 省级）……")
    cities = fetch_cities()
    t1 = sum(1 for c in cities if c["tier"] == 1)
    print(f"\n共 {len(cities)} 个城市，其中 tier1（省会/直辖市/热门）= {t1}")

    if args.print:
        for c in cities[: args.print]:
            print(f"  {c['name']:<8} {c['full']:<14} {c['adcode']} {c['province']} t{c['tier']}")
        return

    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": "amap-district-v3",
        "total": len(cities),
        "tier1": t1,
        "cities": cities,
    }
    OUT_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"✅ 已写入 {OUT_FILE}  （{len(cities)} 城 / tier1 {t1}）")


if __name__ == "__main__":
    main()
