"""探测同程门票城市列表页与搜索页。"""
import re
from patchright.sync_api import sync_playwright

CANDIDATES = [
    "https://www.ly.com/scenery/jingdianmenpiao_1/",
    "https://www.ly.com/scenery/list?cityId=0101",
    "https://www.ly.com/scenery/searchlist?keyword=%E6%95%85%E5%AE%AB",
    "https://www.ly.com/scenery/searchlist?keyword=%E6%95%85%E5%AE%AB%E5%8D%9A%E7%89%A9%E9%99%A2",
]

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN", timezone_id="Asia/Shanghai")
    for u in CANDIDATES:
        page = ctx.new_page()
        try:
            page.goto(u, timeout=35000, wait_until="domcontentloaded")
            page.wait_for_timeout(7000)
            final = page.url
            title = page.title()[:50]
            body = page.locator("body").inner_text()
            prices = re.findall(r"[¥￥]\s*[0-9]{1,5}(?:\.[0-9])?(?:起)?", body)
            print("TRY:", u[:70])
            print("  ->", final[:90], "|", title, "| len:", len(body))
            print("  prices:", prices[:12])
        except Exception as e:
            print("TRY:", u[:70], "ERR:", str(e)[:100])
        page.close()
    browser.close()
