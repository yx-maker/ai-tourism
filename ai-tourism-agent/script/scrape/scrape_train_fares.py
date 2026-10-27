# -*- coding: utf-8 -*-
"""
12306 城际火车票价爬虫（免登录，DOM aria-label 提取票价）
每对取当日所有直通车的各席别最低价，输出 captured/train_price.json。

城市来源：script/scrape/cities_cn.json（全国 391 城，由 build_city_list.py 生成）。
**组合数随城市数呈平方增长**，全量 391 城 = 76,245 对，远超可跑规模，
因此默认只跑 tier1（省会 / 直辖市 / 热门旅游城市，82 城 = 3,321 对）；
未收录的城市对请用 --pair 按需补抓，结果同样落盘并同步到 Java 票价表。

用法：
    python scrape_train_fares.py                     # tier1 增量跑（已有缓存自动跳过）
    python scrape_train_fares.py --pairs 10          # 只跑前 10 对试跑
    python scrape_train_fares.py --pair 广州 福州    # 按需补抓单对（全国任意城市）
    python scrape_train_fares.py --cities 厦门 泉州  # 指定城市两两组合
    python scrape_train_fares.py --tier 2            # 扩到全部 391 城（会提示组合数）
    python scrape_train_fares.py --force             # 忽略缓存强制重抓（刷新实时票价）
"""
import argparse
import itertools
import json
import os
import random
import re
import sys
import time
from datetime import date, timedelta
from pathlib import Path

from patchright.sync_api import sync_playwright

HERE = Path(__file__).parent
PROFILE_DIR = HERE / "browser_profile"
OUT_FILE = HERE / "captured" / "train_price.json"
CITY_LIST_FILE = HERE / "cities_cn.json"

# 12306 预售期约 15 天：取「今天 + 10 天」保证有票可查。
# 必须随运行日期自动滚动——写死日期会随时间失效，导致抓不到票、价格变陈旧。
QUERY_DATE = (date.today() + timedelta(days=10)).isoformat()
ARIA_RE = re.compile(r"([一二三四五等座商务座特等座软卧硬卧软座硬座]+?座)?票价(\d+(?:\.\d+)?)元，余票")


def load_cities(tier=None, names=None) -> list:
    """从全国城市清单加载城市名（tier1=省会/直辖市/热门，tier2=全部）"""
    if not CITY_LIST_FILE.exists():
        print(f"[error] 城市清单不存在：{CITY_LIST_FILE}\n"
              f"        请先运行：python build_city_list.py", file=sys.stderr)
        sys.exit(1)
    data = json.loads(CITY_LIST_FILE.read_text(encoding="utf-8"))
    cities = data.get("cities") or []
    if tier:
        cities = [c for c in cities if c.get("tier") == tier]
    return [c.get("name") for c in cities if c.get("name")]


def resolve_station(city: str, codes: dict):
    """城市名 → 12306 站电报码。

    全国 391 城无法逐一硬编码站名映射，改为按优先级在站码表里自动解析：
    精确匹配 → 前缀匹配（如「福州」→「福州」/「福州南」）→ 别名回退。
    """
    if not city:
        return None
    if city in codes:
        return codes[city], city
    # 前缀匹配：取以城市名开头的第一个客运站（数字标记 2/3 为办理客运的站）
    for name, code in codes.items():
        if name.startswith(city):
            return code, name
    return None


def load_result() -> dict:
    if OUT_FILE.exists():
        return json.loads(OUT_FILE.read_text(encoding="utf-8"))
    return {}


def save_result(r: dict):
    OUT_FILE.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")


def fetch_station_codes(page) -> dict:
    """从 station_name.js 解析 站名→电报码"""
    page.goto("https://kyfw.12306.cn/otn/resources/js/framework/station_name.js",
              timeout=60000, wait_until="domcontentloaded")
    text = page.evaluate("() => document.body.innerText")
    # 格式: @bjb|北京北|VAP|beijingbei|bjb|0:...
    codes = {}
    for m in re.finditer(r"\|([^|]+)\|([A-Z]{3})\|[^|]+\|[^|]+\|(\d)", text):
        name, code = m.group(1), m.group(2)
        codes.setdefault(name, code)
    return codes


def parse_rows(page) -> list:
    """从查询结果 DOM 提取车次与票价"""
    return page.evaluate(
        """() => {
            const out = [];
            document.querySelectorAll('#queryLeftTable tr[id]').forEach(tr => {
                const num = tr.querySelector('a.number')?.innerText?.trim();
                if (!num) return;
                const trains = {code: num};
                // 每个席别 td 的 aria-label: "G531次列车，商务座票价1744元，余票5"
                tr.querySelectorAll('td[aria-label]').forEach(td => {
                    const aria = td.getAttribute('aria-label') || '';
                    const m = aria.match(/([\u4e00-\u9fa5]{2,3}座|硬座|软座|硬卧|软卧|无座)票价([0-9.]+)元/);
                    if (m) trains[m[1]] = parseFloat(m[2]);
                });
                // yp_info_new 兜底: 9 + 每组10位 [4位价格][5位余票][席别码]
                const yp = tr.getAttribute('yp_info_new') || '';
                if (yp.length > 10) trains['yp'] = yp;
                out.push(trains);
            });
            return out;
        }"""
    )


def query_pair(page, a_code, b_code, a_name, b_name) -> list:
    url = (f"https://kyfw.12306.cn/otn/leftTicket/init?linktypeid=dc"
           f"&fs={a_name},{a_code}&ts={b_name},{b_code}&date={QUERY_DATE}&flag=N,N")
    page.goto(url, timeout=45000, wait_until="domcontentloaded")
    page.wait_for_timeout(random.randint(2500, 4000))
    try:
        page.click("#query_ticket", timeout=4000)
    except Exception:
        pass
    page.wait_for_timeout(random.randint(5000, 8000))
    # 行数判定：有行=成功；无行再看是否真风控（12306 页头常驻"请登录注册"，不能作为判据）
    rows = parse_rows(page)
    if rows:
        return rows
    body = page.evaluate("() => document.body.innerText")
    if "请输入验证码" in body or "验证码已过期" in body:
        return [{"_error": "risk_control", "page": body[:60]}]
    return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", type=int, default=0, help="只跑前 N 对（0=全量）")
    ap.add_argument("--reverse", action="store_true", help="也抓反向")
    ap.add_argument("--force", action="store_true",
                    help="忽略缓存，强制重抓（刷新实时票价用；正常增量跑不需要）")
    ap.add_argument("--tier", type=int, choices=[1, 2], default=1,
                    help="城市层级：1=省会/直辖市/热门（82 城，默认）；2=全部 391 城")
    ap.add_argument("--cities", nargs="+", help="指定城市，两两组合（如 --cities 厦门 泉州）")
    ap.add_argument("--pair", nargs=2, metavar=("FROM", "TO"),
                    help="按需补抓单对，如 --pair 广州 福州")
    ap.add_argument("--pending", action="store_true",
                    help="补抓 pending_pairs.json 中累积的缺失城市对（由预算服务自动记录）")
    args = ap.parse_args()

    # ---- 组装待抓城市对 ----
    if args.pair:
        pairs = [(args.pair[0], args.pair[1])]
    elif args.pending:
        pend_file = HERE / "pending_pairs.json"
        if not pend_file.exists():
            print("[info] 暂无待抓城市对（pending_pairs.json 不存在）")
            return
        pend = json.loads(pend_file.read_text(encoding="utf-8"))
        pairs = []
        for k in pend.get("pairs") or []:
            if "-" in k:
                a, b = k.split("-", 1)
                pairs.append((a, b))
        if not pairs:
            print("[info] 待抓队列为空")
            return
        print(f"待抓队列：{len(pairs)} 对（累积于 {pend.get('updated_at')}）")
    elif args.cities:
        pairs = list(itertools.combinations(args.cities, 2))
    else:
        cities = load_cities(tier=args.tier)
        pairs = list(itertools.combinations(cities, 2))
        if args.tier == 2:
            print(f"[!] 全量 {len(cities)} 城 = {len(pairs)} 对，按每对 ~15s 需 "
                  f"{len(pairs) * 15 / 3600:.0f} 小时；可中断，重跑自动续传缓存。")
    if args.reverse:
        pairs += [(b, a) for a, b in pairs]
    if args.pairs:
        pairs = pairs[: args.pairs]

    result = load_result()
    todo = [p for p in pairs
            if args.force or f"{p[0]}-{p[1]}" not in result
            or result[f"{p[0]}-{p[1]}"].get("_error")]
    print(f"共 {len(pairs)} 对，已有 {len(result)} 对缓存，本轮待抓 {len(todo)} 对")
    if not todo:
        print("无待抓城市对（全部已缓存）；加 --force 可强制重抓")
        return

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False, viewport=None,
            locale="zh-CN", timezone_id="Asia/Shanghai",
            args=["--start-maximized", "--window-position=2000,0", "--no-first-run"])
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        print("拉取站码表……")
        codes = fetch_station_codes(page)
        print(f"站码 {len(codes)} 个")

        done = 0
        for a, b in todo:
            key = f"{a}-{b}"
            ra, rb = resolve_station(a, codes), resolve_station(b, codes)
            if not ra or not rb:
                print(f"[skip] {key}: 站码缺失（{a}={'有' if ra else '无'}，"
                      f"{b}={'有' if rb else '无'}）")
                continue
            a_code, a_name = ra
            b_code, b_name = rb
            rows = query_pair(page, a_code, b_code, a_name, b_name)
            if rows and rows[0].get("_error"):
                print(f"[!!] {key}: 风控，暂停 60s")
                time.sleep(60)
                result[key] = {"_error": "risk_control"}
                save_result(result)
                continue
            if not rows:
                print(f"[--] {key}: 无直通车")
                result[key] = {"date": QUERY_DATE, "train_count": 0, "min_price": {}, "trains": []}
                save_result(result)
                continue
            # 汇总各席别最低价
            min_price = {}
            for r in rows:
                for seat, v in r.items():
                    if seat in ("code", "yp"):
                        continue
                    if seat not in min_price or v < min_price[seat]:
                        min_price[seat] = v
            result[key] = {
                "date": QUERY_DATE,
                "train_count": len(rows),
                "min_price": min_price,
                "trains": rows[:5],
            }
            done += 1
            print(f"[{done}/{len(pairs)}] {key}: {len(rows)} 趟 | 最低 {min_price}")
            save_result(result)
            time.sleep(random.uniform(3.0, 6.0))

        ctx.close()

    # 待抓队列：剔除本轮已成功/确认无车的城市对，其余保留下次再试
    if args.pending:
        rest = [k for k in (pend.get("pairs") or [])
                if not (result.get(k) and not result[k].get("_error"))]
        pend_file.write_text(json.dumps({"pairs": rest, "updated_at": QUERY_DATE},
                                        ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"待抓队列剩余 {len(rest)} 对")

    print(f"\n===== 完成：{len(result)} 对 → {OUT_FILE.name} =====")


if __name__ == "__main__":
    main()
