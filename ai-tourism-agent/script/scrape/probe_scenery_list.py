"""深入探测 SceneryList.aspx 页面结构与数据。"""
import re
from patchright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN", timezone_id="Asia/Shanghai")
    page = ctx.new_page()
    page.goto("https://www.ly.com/scenery/SceneryList.aspx?cityid=1", timeout=35000, wait_until="domcontentloaded")
    page.wait_for_timeout(10000)
    html = page.content()
    with open(r"C:\Users\28948\Desktop\毕业论文\ai-tourism-agent\script\scrape\captured\tc_scenerylist.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("len:", len(html))
    body = page.locator("body").inner_text()
    print("body len:", len(body))
    # 景点卡
    cards = page.locator("a[href*=BookSceneryTicket]")
    print("ticket links:", cards.count())
    # 名字样例
    names = re.findall(r'BookSceneryTicket_(\d+)\.html[^>]*>([^<]{3,25})<', html)
    print("names:", names[:10])
    prices = re.findall(r"[¥￥]\s*([0-9]{1,5}(?:\.[0-9])?)", html)
    print("prices:", prices[:15])
    browser.close()
