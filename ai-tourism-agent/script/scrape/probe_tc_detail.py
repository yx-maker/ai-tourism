"""探测酒店详情页价格展示。"""
from patchright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN", timezone_id="Asia/Shanghai")
    page = ctx.new_page()
    page.goto("https://www.ly.com/hotel/hoteldetail?hotelId=91244394&inDate=2026-10-24&outDate=2026-10-25",
              timeout=45000, wait_until="domcontentloaded")
    page.wait_for_timeout(10000)
    body = page.locator("body").inner_text()
    # 找价格相关行
    lines = [l.strip() for l in body.split("\n") if ("¥" in l or "￥" in l) and len(l.strip()) < 30]
    print("price lines:", lines[:20])
    # 保存页面
    with open(r"C:\Users\28948\Desktop\毕业论文\ai-tourism-agent\script\scrape\captured\tc_detail.html", "w", encoding="utf-8") as f:
        f.write(page.content())
    print("len:", len(body))
    browser.close()
