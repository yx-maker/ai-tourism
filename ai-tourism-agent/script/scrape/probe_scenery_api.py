"""拦截 /scenery/ 首页与门票交互的 XHR，找门票列表 API。"""
import json
from patchright.sync_api import sync_playwright

xhrs = []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN", timezone_id="Asia/Shanghai")
    page = ctx.new_page()
    def on_resp(resp):
        u = resp.url
        if ("tapi" in u or "scenery" in u) and "json" in (resp.headers.get("content-type") or "") and "scenery/" not in u[:30]:
            try:
                body = resp.text()
                if body and len(body) > 80:
                    xhrs.append({"url": u[:250], "len": len(body), "body": body[:1200]})
            except Exception:
                pass
    page.on("response", on_resp)
    page.goto("https://www.ly.com/scenery/", timeout=35000, wait_until="domcontentloaded")
    page.wait_for_timeout(8000)
    # 触发城市切换看看有没有交互 API
    try:
        page.click("text=北京", timeout=3000)
        page.wait_for_timeout(4000)
    except Exception:
        pass
    with open(r"C:\Users\28948\Desktop\毕业论文\ai-tourism-agent\script\scrape\captured\tc_scenery_xhr.json", "w", encoding="utf-8") as f:
        json.dump(xhrs, f, ensure_ascii=False, indent=1)
    for x in xhrs[:25]:
        print(x["url"][:160])
    browser.close()
