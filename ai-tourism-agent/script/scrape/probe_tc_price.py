"""探测酒店价格异步加载：监听 XHR + 等待后 dump 卡片价格。"""
import json, re
from patchright.sync_api import sync_playwright

URL = "https://www.ly.com/hotel/hotellist?cityId=0101"
xhrs = []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN", timezone_id="Asia/Shanghai")
    page = ctx.new_page()

    def on_resp(resp):
        u = resp.url
        if any(k in u for k in ("price", "Price", "hotel", "list", "api")) and ("json" in (resp.headers.get("content-type") or "")):
            try:
                body = resp.text()
                if body and len(body) > 100:
                    xhrs.append({"url": u, "len": len(body), "body": body[:3000]})
            except Exception:
                pass

    page.on("response", on_resp)
    page.goto(URL, timeout=45000, wait_until="domcontentloaded")
    page.wait_for_timeout(15000)

    # dump 卡片价格
    cards = page.locator("a.listBox")
    n = cards.count()
    print("cards:", n)
    for i in range(min(n, 5)):
        c = cards.nth(i)
        name = c.locator("dd").first.inner_text() if c.locator("dd").count() else "?"
        price = c.locator(".discountPrice").first.inner_text() if c.locator(".discountPrice").count() else "?"
        print(f"[{i}] {name} | price={price!r}")

    with open(r"C:\Users\28948\Desktop\毕业论文\ai-tourism-agent\script\scrape\captured\tc_price_xhr.json", "w", encoding="utf-8") as f:
        json.dump(xhrs, f, ensure_ascii=False, indent=1)
    print("xhr captured:", len(xhrs))
    for x in xhrs[:15]:
        print("URL:", x["url"][:150])
    browser.close()
