"""正确交互探测：hover 展开城市面板 → 点击北京 → 拦截 XHR。"""
import json, re
from patchright.sync_api import sync_playwright

xhrs = []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN", timezone_id="Asia/Shanghai")
    page = ctx.new_page()
    def on_resp(resp):
        u = resp.url
        if "json" in (resp.headers.get("content-type") or "") and len(u) > 60:
            try:
                body = resp.text()
                if body and len(body) > 200:
                    xhrs.append({"url": u[:220], "body": body[:600]})
            except Exception:
                pass
    page.on("response", on_resp)

    page.goto("https://www.ly.com/scenery/", timeout=40000, wait_until="domcontentloaded")
    page.wait_for_timeout(9000)

    # 1. hover 城市入口
    city_span = page.locator("span.city").first
    try:
        city_span.hover(timeout=5000)
        page.wait_for_timeout(2000)
        print("hover ok")
    except Exception as e:
        print("hover err:", str(e)[:100])

    # 2. 点击北京（可见面板中的）
    try:
        bj = page.locator("a.ca-l", has_text="北京").first
        bj.click(timeout=6000)
        print("click ok")
        page.wait_for_timeout(9000)
    except Exception as e:
        print("click err:", str(e)[:150])

    # 3. dump 卡片名
    names = page.eval_on_selector_all(
        "a.item_a .name_span", "els => els.map(e => e.innerText.trim()).slice(0, 12)")
    print("cards:", names)

    # 4. XHR
    print("--- xhr:")
    for x in xhrs[-12:]:
        print(x["url"][:140])
    with open(r"C:\Users\28948\Desktop\毕业论文\ai-tourism-agent\script\scrape\captured\tc_city_switch_xhr.json", "w", encoding="utf-8") as f:
        json.dump(xhrs, f, ensure_ascii=False, indent=1)
    browser.close()
