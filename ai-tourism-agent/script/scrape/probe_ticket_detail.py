"""验证门票详情页：价格可见性 + 同城推荐。"""
import re
from patchright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN", timezone_id="Asia/Shanghai")
    page = ctx.new_page()
    page.goto("https://www.ly.com/scenery/BookSceneryTicket_3387.html", timeout=40000, wait_until="domcontentloaded")
    page.wait_for_timeout(9000)
    print("url:", page.url[:90])
    print("title:", page.title()[:60])
    html = page.content()
    print("len:", len(html))
    with open(r"C:\Users\28948\Desktop\毕业论文\ai-tourism-agent\script\scrape\captured\tc_ticket_detail.html", "w", encoding="utf-8") as f:
        f.write(html)
    # 价格
    prices = re.findall(r"[¥￥]\s*[0-9]{1,5}(?:\.[0-9])?(?:起)?", html)
    print("prices:", prices[:12])
    # 同城推荐
    rec = re.findall(r'BookSceneryTicket_(\d+)\.html[^>]*>\s*([^<]{3,20})\s*<', html)
    print("rec links:", list(dict.fromkeys(rec))[:15])
    browser.close()
