"""尝试多个候选 URL，找能渲染酒店列表的页面。"""
import re
from patchright.sync_api import sync_playwright

CANDIDATES = [
    "https://www.ly.com/hotel/hotellist?cityId=0101",
    "https://www.ly.com/hotel/hotellist?city=0101",
    "https://www.ly.com/hotel/guonei1101/",
    "https://www.ly.com/hotel/guonei-1101/",
    "https://www.ly.com/hoteldetail/beijing/",
]

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN", timezone_id="Asia/Shanghai")
    page = ctx.new_page()
    for url in CANDIDATES:
        try:
            resp = page.goto(url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(6000)
            html = page.content()
            names = re.findall(r'>([\u4e00-\u9fa5A-Za-z0-9()·]{6,32}(?:酒店|公寓|客栈|宾馆)[^<]{0,10})<', html)
            prices = re.findall(r'[¥￥]\s*(\d{2,5})', html)
            print(f"{url}\n  -> status={resp.status if resp else '?'} final={page.url[:80]} 酒店名={len(names)} 价格={len(prices)}")
            if names[:2]:
                print("  样本:", names[:2], prices[:5])
        except Exception as e:
            print(f"{url}\n  -> ERR {str(e)[:70]}")
    browser.close()
