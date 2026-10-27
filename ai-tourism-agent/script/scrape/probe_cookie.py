"""尝试城市 Cookie：设 cookie 后刷新看卡片是否变化。"""
import json
from patchright.sync_api import sync_playwright

COOKIES_TO_TRY = [
    {"name": "thcityid", "value": "53"},
    {"name": "cityid", "value": "53"},
    {"name": "scenery_cityid", "value": "53"},
    {"name": "tc_city", "value": "53"},
]

def get_cards(page):
    return page.evaluate("""() => {
        const out = [];
        document.querySelectorAll('a.item_a').forEach(a => {
            const n = a.querySelector('.name_span');
            const pr = a.querySelector('.tcPrice em');
            if (n) out.push(n.innerText.trim() + (pr ? ':' + pr.innerText : ''));
        });
        return out.slice(0, 10);
    }""")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN", timezone_id="Asia/Shanghai")
    ctx.add_cookies([{**c, "domain": ".ly.com", "path": "/"} for c in COOKIES_TO_TRY])
    page = ctx.new_page()
    page.goto("https://www.ly.com/scenery/", timeout=40000, wait_until="domcontentloaded")
    page.wait_for_timeout(9000)
    print("with cookies cards:", get_cards(page))
    # 当前城市文本
    city_text = page.evaluate("() => document.querySelector('span.city')?.innerText")
    print("span.city:", city_text)
    browser.close()
