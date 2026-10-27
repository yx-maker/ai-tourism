"""同程门票价格爬取 + t_poi 补库脚本 v3（运维工具，非运行时组件）。

数据源结论（2026-10-23 三轮探测后的最终方案）：
    同程旅行门票频道移动端城市列表页
        https://m.ly.com/scenery_2/#/pages/list/list?cityId={cid}
    无需登录即可见每景点「¥N 起」**纯门票起价**（杜甫草堂 50 ✔、
    大熊猫基地 50 ✔、成都欢乐谷 230 ✔），与 PC 详情页头部
    「最低可售商品价」（混入讲解套餐/联票，故宫 150 ✗）不同，
    语义与 t_poi.ticket_price（成人参考票价）一致。

    弃用的路径（记录教训）：
    - PC 城市面板切换：隐藏面板 + 无有效城市 Cookie，SPA 点击不稳定；
    - PC 详情页 BFS 扩散：头部起价语义污染（什刹海 110 是游船价），
      仅保留 captured/tc_tickets.json 作为景点索引参考；
    - 移动端 getAllResourceOutWithMerger SKU：需逐景点二次请求，
      且部分景点（颐和园）同程只有套餐无纯门票。

抓取流程：
    1. PC 首页一次拿城市 id 映射（a[cityid]，366 城）；
    2. 移动端 UA 依次访问各城市列表页，解析 .resourseBox 卡片
       （名称 = 首个文本，价格 = 尾部「¥ N 起」）；
    3. 名称（归一化）+ 城市双重匹配 t_poi；
    4. 只写「POI 现价 = 0 且同程价 > 0」——不覆盖已有权威价格，
       免费/未上架（价格 0 或缺失）自动跳过，宁缺毋滥。

用法：
    # 预演（默认，不写库）
    python script/scrape_tc_tickets.py

    # 实际写入
    python script/scrape_tc_tickets.py --apply

    # 复用已有抓取结果
    python script/scrape_tc_tickets.py --no-scrape

    # 限定城市
    python script/scrape_tc_tickets.py --apply --cities 成都 杭州

依赖：patchright、pymysql
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import time
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional, Tuple

SCENERY_HOME = "https://www.ly.com/scenery/"
MOBILE_LIST = "https://m.ly.com/scenery_2/#/pages/list/list?cityId={cid}&refid=2000411121"
OUT_DIR = Path(__file__).resolve().parent / "captured"
OUT_JSON = OUT_DIR / "tc_tickets_city.json"

DEFAULT_DB = dict(
    host=os.getenv("DB_HOST", "127.0.0.1"),
    port=int(os.getenv("DB_PORT", "3306")),
    user=os.getenv("DB_USER", "root"),
    password=os.getenv("DB_PASSWORD", "123456"),
    database=os.getenv("DB_NAME", "aitourism"),
)

CITY_WAIT_MS = 12000        # 城市列表页渲染等待（Taro SPA 较慢）
MAX_RETRY = 2
INTERVAL = (3.0, 6.0)       # 城市间随机间隔（礼貌抓取）

# PC 首页城市映射提取
CITY_LIST_JS = """
() => {
  const out = {};
  document.querySelectorAll('a[cityid]').forEach(a => {
    const n = a.innerText.trim();
    if (n && a.getAttribute('cityid') !== 'null') out[n] = a.getAttribute('cityid');
  });
  document.querySelectorAll('a.ca-l[mid]').forEach(a => {
    const n = a.innerText.trim();
    if (n && a.getAttribute('mid') !== 'null') out[n] = a.getAttribute('mid');
  });
  return out;
}
"""

# 移动端城市列表卡片提取
MOBILE_CARDS_JS = """
() => {
  const out = [];
  document.querySelectorAll('.resourseBox').forEach(box => {
    const texts = [];
    box.querySelectorAll('taro-text-core').forEach(t => {
      const v = (t.innerText || '').trim();
      if (v) texts.push(v);
    });
    if (texts.length >= 3) out.push(texts);
  });
  return out;
}
"""


@dataclass
class TicketCard:
    city: str
    name: str
    price: Optional[float]
    raw: List[str]

    def to_dict(self) -> dict:
        return self.__dict__.copy()


# ---------------------------------------------------------------------------
# 名称处理与匹配
# ---------------------------------------------------------------------------
def normalize(name: str) -> str:
    s = re.sub(r"[\s（）()【】\[\]·]", "", name or "")
    s = re.sub(r"门票(预订)?$", "", s)
    s = re.sub(r"(风景名胜区|风景区|旅游区|博物馆)?$", lambda m: "" if m.group(0) == "博物馆" else m.group(0), s) if False else s
    s = re.sub(r"(风景名胜区|风景区|旅游区|景区)$", "", s)
    return s


def _city_eq(city_a: str, city_b: Optional[str]) -> bool:
    if not city_b:
        return False
    strip = lambda s: re.sub(r"[市区]$", "", (s or "").strip())
    return strip(city_a) == strip(city_b)


# 同程名比 POI 名多出的部分若含这些词，说明是衍生商品（游船/索道等），非景点本体
DERIVED_SUFFIX = re.compile(r"游船|索道|缆车|夜游|漂流|温泉|游乐园|欢乐世界|水世界|飞行|观光| theater|影城|表演|秀")


def match_name(poi_name: str, pool: List[TicketCard]) -> Optional[Tuple[TicketCard, str]]:
    pn = normalize(poi_name)
    if not pn:
        return None
    best: Optional[TicketCard] = None
    kind = ""
    for c in pool:
        cn = normalize(c.name)
        if not cn:
            continue
        if cn == pn:
            if best is None or len(c.name) < len(best.name):
                best, kind = c, "exact"
        elif best is None and (cn in pn or pn in cn) and min(len(cn), len(pn)) >= 2:
            # 差异部分含衍生词则拒绝（洱海 → 洱海游船 ✗）
            diff = cn.replace(pn, "") if pn in cn else pn.replace(cn, "")
            if DERIVED_SUFFIX.search(diff):
                continue
            best, kind = c, "contains"
    return (best, kind) if best else None


def parse_card(texts: List[str]) -> Tuple[str, Optional[float]]:
    """卡片文本流 → (名称, 起价)。价格 = 尾部「¥ N 起」的 N。"""
    name = texts[0]
    price = None
    for i, t in enumerate(texts):
        if t == "¥" and i + 1 < len(texts):
            try:
                price = float(texts[i + 1])
            except ValueError:
                pass
    return name, price


# ---------------------------------------------------------------------------
# 抓取
# ---------------------------------------------------------------------------
def get_city_map() -> Dict[str, str]:
    """PC 首页一次拿城市 id 映射。"""
    from patchright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            viewport={"width": 1440, "height": 900}, locale="zh-CN", timezone_id="Asia/Shanghai"
        )
        page = ctx.new_page()
        for attempt in range(MAX_RETRY + 1):
            try:
                page.goto(SCENERY_HOME, timeout=40000, wait_until="domcontentloaded")
                page.wait_for_timeout(9000)
                if len(page.content()) > 50000:
                    mapping = page.evaluate(CITY_LIST_JS)
                    browser.close()
                    return mapping
                print(f"  [retry {attempt}] PC 首页空响应")
            except Exception as e:
                print(f"  [retry {attempt}] err: {str(e)[:70]}")
            time.sleep(8)
        browser.close()
    return {}


def scrape_cities(cities: List[str], city_map: Dict[str, str]) -> List[TicketCard]:
    """移动端 UA 逐城市抓列表卡。"""
    from patchright.sync_api import sync_playwright

    results: List[TicketCard] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        iphone = p.devices["iPhone 13"]
        ctx = browser.new_context(**iphone, locale="zh-CN", timezone_id="Asia/Shanghai")
        page = ctx.new_page()

        for city in cities:
            cid = city_map.get(city)
            if not cid:
                print(f"跳过 {city}：无城市 id")
                continue
            got = 0
            for attempt in range(MAX_RETRY + 1):
                try:
                    page.goto(MOBILE_LIST.format(cid=cid), timeout=40000,
                              wait_until="domcontentloaded")
                    page.wait_for_timeout(CITY_WAIT_MS)
                    cards = page.evaluate(MOBILE_CARDS_JS)
                    if cards:
                        for texts in cards:
                            name, price = parse_card(texts)
                            results.append(TicketCard(city=city, name=name,
                                                      price=price, raw=texts[:12]))
                            got += 1
                        break
                    print(f"  {city} attempt{attempt}: 空列表")
                except Exception as e:
                    print(f"  {city} attempt{attempt} err: {str(e)[:70]}")
                time.sleep(8)
            print(f"{city}(id={cid}): {got} 张卡")
            time.sleep(random.uniform(*INTERVAL))

        browser.close()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump([c.to_dict() for c in results], f, ensure_ascii=False, indent=1)
    print(f"\n共 {len(results)} 条 → {OUT_JSON}")
    return results


# ---------------------------------------------------------------------------
# 数据库
# ---------------------------------------------------------------------------
def load_pois(cities: Optional[List[str]]):
    import pymysql

    conn = pymysql.connect(charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor, **DEFAULT_DB)
    try:
        with conn.cursor() as cur:
            if cities:
                ph = ",".join(["%s"] * len(cities))
                cur.execute(
                    f"SELECT id, poi_name, city_name, ticket_price FROM t_poi WHERE city_name IN ({ph})",
                    cities,
                )
            else:
                cur.execute("SELECT id, poi_name, city_name, ticket_price FROM t_poi")
            return cur.fetchall()
    finally:
        conn.close()


def apply_updates(rows: List[Tuple[int, Decimal]]):
    import pymysql

    conn = pymysql.connect(charset="utf8mb4", **DEFAULT_DB)
    try:
        with conn.cursor() as cur:
            for poi_id, price in rows:
                cur.execute(
                    "UPDATE t_poi SET ticket_price=%s, modify_time=NOW() WHERE id=%s",
                    (str(price), poi_id),
                )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="同程门票爬取(移动端城市列表) + t_poi 补库")
    ap.add_argument("--apply", action="store_true", help="实际写库（默认仅预演）")
    ap.add_argument("--overwrite", action="store_true",
                    help="全量刷新：同程价>0 即覆盖已有价（默认只补现价=0 的缺口）")
    ap.add_argument("--no-scrape", action="store_true", help="跳过抓取，用已有 captured/tc_tickets_city.json")
    ap.add_argument("--cities", nargs="*", help="限定城市（默认取 t_poi 全部城市）")
    args = ap.parse_args()

    if args.no_scrape and OUT_JSON.exists():
        data = json.loads(OUT_JSON.read_text(encoding="utf-8"))
        cards = [TicketCard(**d) for d in data]
        print(f"载入已有抓取结果: {len(cards)} 条")
    else:
        city_map = get_city_map()
        print(f"城市映射: {len(city_map)} 个")
        if not city_map:
            print("PC 首页被拦，无法获取城市映射，终止。")
            return
        with open(OUT_DIR / "tc_city_map_full.json", "w", encoding="utf-8") as f:
            json.dump(city_map, f, ensure_ascii=False, indent=1)

        target_cities = args.cities or []
        if not target_cities:
            pois_all = load_pois(None)
            target_cities = sorted({p["city_name"] for p in pois_all})
        cards = scrape_cities(target_cities, city_map)

    if not cards:
        print("未抓到任何数据。")
        return

    pois = load_pois(args.cities or None)
    by_city: Dict[str, List[TicketCard]] = {}
    for c in cards:
        by_city.setdefault(c.city, []).append(c)

    print(f"\n===== 匹配预演（{len(pois)} 个 POI）=====")
    updates = []
    for poi in pois:
        city_pool = [c for c in by_city.get(poi["city_name"], []) if _city_eq(poi["city_name"], c.city)]
        hit = match_name(poi["poi_name"], city_pool)
        if not hit:
            continue
        card, kind = hit
        old = Decimal(str(poi["ticket_price"]))
        if old != 0 and not args.overwrite:
            print(f"[跳过-已有价] {poi['city_name']} {poi['poi_name']}: {old}")
            continue
        if card.price is None or card.price <= 0:
            print(f"[跳过-同程免费/未上架] {poi['city_name']} {poi['poi_name']}")
            continue
        new = Decimal(str(card.price))
        if old != 0 and new != old:
            drift = abs(new - old) / old * 100
            mark = "校准" if drift <= 20 else "!!大幅差异"
            print(f"[overwrite-{kind}] {poi['city_name']} {poi['poi_name']}: {old} → {new} ({mark} {drift.quantize(Decimal('0.1'))}%)")
        updates.append((poi["id"], new))
        print(f"[{kind}] {poi['city_name']} {poi['poi_name']}: {old} → {new}  (同程:{card.name})")

    print(f"\n共 {len(updates)} 条待更新")
    if args.apply and updates:
        apply_updates(updates)
        print("已写库 ✔")
    else:
        print("预演模式，未写库。加 --apply 执行写入。")


if __name__ == "__main__":
    main()
