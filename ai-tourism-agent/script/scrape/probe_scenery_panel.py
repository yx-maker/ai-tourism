"""慢速重试：门票首页 → 找城市面板结构。"""
import re, time
from patchright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN", timezone_id="Asia/Shanghai")
    page = ctx.new_page()

    html = None
    for attempt in range(3):
        try:
            page.goto("https://www.ly.com/scenery/", timeout=35000, wait_until="domcontentloaded")
            page.wait_for_timeout(9000)
            html = page.content()
            if len(html) > 50000:
                print(f"attempt {attempt}: OK len={len(html)}")
                break
            print(f"attempt {attempt}: blocked len={len(html)}")
        except Exception as e:
            print(f"attempt {attempt}: err {str(e)[:80]}")
        time.sleep(15)

    if html and len(html) > 50000:
        with open(r"C:\Users\28948\Desktop\毕业论文\ai-tourism-agent\script\scrape\captured\tc_scenery_home.html", "w", encoding="utf-8") as f:
            f.write(html)
        # 城市面板结构：找"热门城市"/城市名列表附近 DOM
        m = re.search(r'热门城市', html)
        if m:
            seg = html[m.start():m.start()+2500]
            print(seg[:2200])
        else:
            print("no 热门城市 marker; body head:")
            print(re.sub(r'<[^>]+>', ' ', html)[:400])
    browser.close()
