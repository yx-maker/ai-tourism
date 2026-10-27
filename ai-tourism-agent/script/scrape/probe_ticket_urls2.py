"""批量试探同程门票搜索/城市列表 URL。"""
import re
from patchright.sync_api import sync_playwright

CANDIDATES = [
    "https://www.ly.com/scenery/ScenerySearchList.aspx?keyword=%E6%95%85%E5%AE%AB",
    "https://www.ly.com/scenery/searchresult?keyword=%E6%95%85%E5%AE%AB",
    "https://s.ly.com/scenery/search?keyword=%E6%95%85%E5%AE%AB",
    "https://www.ly.com/scenery/citylist_1/",
    "https://www.ly.com/scenery/jingdian1/",
    "https://www.ly.com/scenery/beijing1/",
    "https://www.ly.com/scenery/c_1/",
    "https://www.ly.com/scenery/SceneryList.aspx?cityid=1",
]

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN", timezone_id="Asia/Shanghai")
    for u in CANDIDATES:
        page = ctx.new_page()
        try:
            page.goto(u, timeout=25000, wait_until="domcontentloaded")
            page.wait_for_timeout(5000)
            final = page.url
            title = page.title()[:40]
            if "404" in final or "404" in title:
                print("404  ", u[:75])
            else:
                body = page.locator("body").inner_text()
                prices = re.findall(r"[¥￥]\s*[0-9]{1,5}(?:\.[0-9])?(?:起)?", body)
                print("OK   ", u[:75], "->", final[:70], "|", title, "| prices:", prices[:8])
        except Exception as e:
            print("ERR  ", u[:75], str(e)[:80])
        page.close()
    browser.close()
