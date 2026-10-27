"""dump 酒店卡 DOM 结构，确定名称/价格/星级提取选择器。"""
from patchright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN", timezone_id="Asia/Shanghai")
    page = ctx.new_page()
    page.goto("https://www.ly.com/hotel/hotellist?cityId=0101", timeout=45000, wait_until="domcontentloaded")
    page.wait_for_timeout(8000)
    # 等酒店卡出现
    try:
        page.wait_for_selector(".hotelItem, .hotel-item, [class*=hotelItem]", timeout=15000)
    except Exception:
        pass
    # 找第一张酒店卡的 HTML
    card = page.locator("[class*=hotelItem], [class*=hotel-item]").first
    try:
        html = card.evaluate("el => el.outerHTML")
        print(html[:2500])
    except Exception as e:
        print("card err:", e)
    browser.close()
