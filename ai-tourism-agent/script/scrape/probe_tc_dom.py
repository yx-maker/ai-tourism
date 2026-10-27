"""dump 列表页实际 DOM：找到含价格的卡片结构。"""
import re
from patchright.sync_api import sync_playwright

URL = "https://www.ly.com/hotel/hotellist?cityId=0101"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN", timezone_id="Asia/Shanghai")
    page = ctx.new_page()
    page.goto(URL, timeout=45000, wait_until="domcontentloaded")
    page.wait_for_timeout(10000)
    html = page.content()
    with open(r"C:\Users\28948\Desktop\毕业论文\ai-tourism-agent\script\scrape\captured\tc_hotellist.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("html saved, len =", len(html))
    # 找含 ¥ 或价格的元素类名
    classes = re.findall(r'class="([^"]+)"', html)
    hot = [c for c in set(classes) if any(k in c.lower() for k in ("hotel", "price", "list", "item", "card"))]
    for c in sorted(hot)[:60]:
        print("CLS:", c)
    # 价格样例
    prices = re.findall(r"[¥￥]\s*[0-9]+", html)
    print("price samples:", prices[:20])
    # 酒店名样例：找 title 属性
    titles = re.findall(r'title="([^"]{4,30})"', html)
    print("title samples:", titles[:20])
    browser.close()
