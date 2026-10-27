"""调用 GETSCENERYLISTYKE 接口获取故宫票品列表。"""
from patchright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN", timezone_id="Asia/Shanghai")
    page = ctx.new_page()
    page.goto("https://www.ly.com/scenery/BookSceneryTicket_3007.html", timeout=35000, wait_until="domcontentloaded")
    page.wait_for_timeout(5000)
    for pid in [3, 5, 14]:
        try:
            resp = page.goto(
                f"https://www.ly.com/scenery/AjaxHelper/AjaxCall.aspx?action=GETSCENERYLISTYKE&cityId=53&productId={pid}&sid=3007",
                timeout=25000)
            body = resp.text() if resp else ""
            print(f"== productId={pid} status={resp.status if resp else None} len={len(body)}")
            print(body[:900])
            # 回到详情页继续用
            page.goto("https://www.ly.com/scenery/BookSceneryTicket_3007.html", timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(2500)
        except Exception as e:
            print(f"pid={pid} err:", str(e)[:100])
    browser.close()
