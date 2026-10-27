# -*- coding: utf-8 -*-
"""
小红书旅游攻略爬虫（需登录态，复用 browser_profile）
对指定城市搜索「{城市} 景点 攻略」，抓取 Top N 笔记的标题+正文+互动数，
输出 captured/xhs_notes.json（增量去重、断点续抓）。

用法：
    python scrape_xhs_notes.py                     # 15 城 × 10 篇
    python scrape_xhs_notes.py --cities 北京 上海   # 指定城市
    python scrape_xhs_notes.py --per-city 8        # 每城篇数
"""
import argparse
import json
import random
import time
from pathlib import Path

from patchright.sync_api import sync_playwright

HERE = Path(__file__).parent
PROFILE_DIR = HERE / "browser_profile"
OUT_FILE = HERE / "captured" / "xhs_notes.json"

CITIES = ["北京", "上海", "广州", "深圳", "成都", "杭州", "武汉", "长沙",
          "西安", "重庆", "厦门", "三亚", "桂林", "丽江", "济南"]

SEARCH_URL = "https://www.xiaohongshu.com/search_result?keyword={kw}&source=web_explore_feed"


def load_notes() -> list:
    if OUT_FILE.exists():
        return json.loads(OUT_FILE.read_text(encoding="utf-8"))
    return []


def save_notes(notes: list):
    OUT_FILE.write_text(json.dumps(notes, ensure_ascii=False, indent=1), encoding="utf-8")


def collect_search_cards(page) -> list:
    """滚动加载并收集笔记卡片（去重，取含 xsec_token 的链接）"""
    seen = {}
    for _ in range(6):  # 滚 6 次
        page.mouse.wheel(0, 2000)
        page.wait_for_timeout(random.randint(1200, 2200))
        cards = page.evaluate(
            """() => {
                const out = [];
                document.querySelectorAll('a[href*="xsec_token"]').forEach(a => {
                    const href = a.getAttribute('href') || '';
                    const m = href.match(/\\/(?:search_result|explore)\\/([0-9a-f]{24})/);
                    if (!m) return;
                    const sec = a.closest('section');
                    const title = sec?.querySelector('.title, .note-text')?.innerText?.trim()
                               || a.innerText.trim().slice(0, 60);
                    out.push({id: m[1], href: href, title: title});
                });
                return out;
            }"""
        )
        for c in cards:
            seen.setdefault(c["id"], c)
    return list(seen.values())


def parse_note(page) -> dict:
    """解析笔记详情页：标题 / 正文 / 互动数 / 发布时间"""
    return page.evaluate(
        """() => {
            const title = document.querySelector('#detail-title, .title')?.innerText?.trim() || document.title.split(' - 小红书')[0];
            const desc = document.querySelector('#detail-desc, .desc')?.innerText?.trim() || '';
            const dateEl = document.querySelector('.date')?.innerText?.trim() || '';
            const interact = {};
            document.querySelectorAll('.engage-bar-container .count, .interact-container .count').forEach(e => {
                interact[e.className] = e.innerText.trim();
            });
            const likes = document.querySelector('.like-wrapper .count')?.innerText?.trim() || '';
            const collects = document.querySelector('.collect-wrapper .count')?.innerText?.trim() || '';
            const comments = document.querySelector('.chat-wrapper .count')?.innerText?.trim() || '';
            return {title, desc, date: dateEl, likes, collects, comments};
        }"""
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cities", nargs="*", default=CITIES)
    ap.add_argument("--per-city", type=int, default=10)
    ap.add_argument("--max-desc", type=int, default=2000, help="正文最大字符数")
    args = ap.parse_args()

    notes = load_notes()
    done_ids = {n["note_id"] for n in notes}
    print(f"已有 {len(notes)} 篇笔记，续抓模式")

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            viewport=None,
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            args=["--start-maximized", "--window-position=2000,0", "--no-first-run",
                  "--disable-blink-features=AutomationControlled"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        for city in args.cities:
            have = sum(1 for n in notes if n["city"] == city)
            if have >= args.per_city:
                print(f"[skip] {city} 已有 {have} 篇")
                continue
            print(f"\n===== {city}（已有 {have} 篇）=====")
            kw = f"{city} 景点 攻略"
            page.goto(SEARCH_URL.format(kw=kw), timeout=60000, wait_until="domcontentloaded")
            page.wait_for_timeout(4000)
            # 登录失效检测
            if page.evaluate("() => /登录后查看/.test(document.body.innerText)"):
                print("!! 登录态失效，请重新运行 login_capture.py")
                break

            cards = collect_search_cards(page)
            print(f"搜索到 {len(cards)} 张卡片")
            added = 0
            for c in cards:
                if added >= args.per_city:
                    break
                if c["id"] in done_ids:
                    continue
                url = "https://www.xiaohongshu.com" + c["href"]
                try:
                    page.goto(url, timeout=45000, wait_until="domcontentloaded")
                    page.wait_for_timeout(random.randint(2500, 4000))
                    data = parse_note(page)
                except Exception as e:
                    print(f"  [err] {c['id'][:12]}: {str(e)[:60]}")
                    continue
                if not data["desc"] or len(data["desc"]) < 50:
                    print(f"  [skip] 正文过短: {data['title'][:24]}")
                    continue
                notes.append({
                    "city": city,
                    "note_id": c["id"],
                    "url": url,
                    "title": data["title"],
                    "date": data["date"],
                    "likes": data["likes"],
                    "collects": data["collects"],
                    "comments": data["comments"],
                    "text": data["desc"][: args.max_desc],
                })
                done_ids.add(c["id"])
                added += 1
                print(f"  [{added}] {data['title'][:30]} 👍{data['likes']}")
                save_notes(notes)  # 每篇落盘，可中断
                time.sleep(random.uniform(2.0, 4.0))
            # 回搜索页前歇一下
            time.sleep(random.uniform(3.0, 6.0))

        ctx.close()

    print(f"\n===== 完成：共 {len(notes)} 篇 → {OUT_FILE.name} =====")


if __name__ == "__main__":
    main()
