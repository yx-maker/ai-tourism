"""试滚动触发价格加载；对比带日期的 URL。"""
import json
from patchright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN", timezone_id="Asia/Shanghai")
    page = ctx.new_page()

    prices_seen = []
    def on_resp(resp):
        u = resp.url
        if "tapi" in u and "json" in (resp.headers.get("content-type") or ""):
            try:
                prices_seen.append({"url": u[:200], "body": resp.text()[:1500]})
            except Exception:
                pass

    page.on("response", on_resp)
    page.goto("https://www.ly.com/hotel/hotellist?cityId=0101&inDate=2026-10-24&outDate=2026-10-25",
              timeout=45000, wait_until="domcontentloaded")
    page.wait_for_timeout(6000)
    # 慢速滚动到底触发懒加载
    for i in range(6):
        page.mouse.wheel(0, 800)
        page.wait_for_timeout(1500)
    page.wait_for_timeout(4000)

    cards = page.locator("a.listBox")
    n = cards.count()
    ok = 0
    for i in range(min(n, 8)):
        c = cards.nth(i)
        name = c.locator("dd").first.inner_text() if c.locator("dd").count() else "?"
        price = c.locator(".discountPrice").first.inner_text() if c.locator(".discountPrice").count() else "?"
        if price and "？" not in price:
            ok += 1
        print(f"[{i}] {name[:25]} | {price!r}")
    print("priced cards:", ok, "/", n)
    with open(r"C:\Users\28948\Desktop\毕业论文\ai-tourism-agent\script\scrape\captured\tc_scroll_xhr.json", "w", encoding="utf-8") as f:
        json.dump(prices_seen, f, ensure_ascii=False, indent=1)
    print("xhr total:", len(prices_seen))
    browser.close()
