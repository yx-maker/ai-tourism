"""探测同程移动端 H5 酒店列表是否展示价格。"""
from patchright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    iphone = p.devices["iPhone 13"]
    ctx = browser.new_context(**iphone, locale="zh-CN", timezone_id="Asia/Shanghai")
    page = ctx.new_page()
    page.goto("https://m.ly.com/hotel/hotellist?cityId=0101&inDate=2026-10-24&outDate=2026-10-25",
              timeout=45000, wait_until="domcontentloaded")
    page.wait_for_timeout(10000)
    url_now = page.url
    print("url:", url_now[:120])
    body = page.locator("body").inner_text()
    lines = [l.strip() for l in body.split("\n") if ("¥" in l or "￥" in l) and len(l.strip()) < 25]
    print("price lines:", lines[:25])
    with open(r"C:\Users\28948\Desktop\毕业论文\ai-tourism-agent\script\scrape\captured\tc_m_list.html", "w", encoding="utf-8") as f:
        f.write(page.content())
    browser.close()
