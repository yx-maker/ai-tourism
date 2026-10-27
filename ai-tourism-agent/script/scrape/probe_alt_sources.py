"""探测：1) 去哪儿酒店列表价格 2) 同程门票频道。"""
import re
from patchright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN", timezone_id="Asia/Shanghai")

    # === 1. 去哪儿酒店 ===
    page = ctx.new_page()
    try:
        page.goto("https://hotel.qunar.com/city/beijing/", timeout=40000, wait_until="domcontentloaded")
        page.wait_for_timeout(9000)
        body = page.locator("body").inner_text()
        prices = re.findall(r"[¥￥]\s*([0-9]{2,5})", body)
        print("QUNAR url:", page.url[:90])
        print("QUNAR prices:", prices[:15])
    except Exception as e:
        print("qunar err:", str(e)[:150])
    page.close()

    # === 2. 同程门票 ===
    page2 = ctx.new_page()
    for u in ["https://www.ly.com/scenery/", "https://piao.ly.com/"]:
        try:
            page2.goto(u, timeout=35000, wait_until="domcontentloaded")
            page2.wait_for_timeout(8000)
            print("TICKET url:", page2.url[:90], "| title:", page2.title()[:40])
            body2 = page2.locator("body").inner_text()
            pr2 = re.findall(r"[¥￥]\s*[0-9]{1,5}", body2)
            print("TICKET prices:", pr2[:15], "| body len:", len(body2))
            break
        except Exception as e:
            print("ticket err:", u[:40], str(e)[:120])
    browser.close()
