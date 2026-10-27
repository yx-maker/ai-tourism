"""探测移动端门票搜索 API。"""
import json
from patchright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    iphone = p.devices["iPhone 13"]
    ctx = browser.new_context(**iphone, locale="zh-CN", timezone_id="Asia/Shanghai")
    page = ctx.new_page()
    xhrs = []
    def on_resp(resp):
        u = resp.url
        if "json" in (resp.headers.get("content-type") or "") and any(
                k in u.lower() for k in ("search", "keyword", "query")):
            try:
                b = resp.text()
                if b and len(b) > 100:
                    xhrs.append({"url": u[:200], "len": len(b), "body": b[:800]})
            except Exception:
                pass
    page.on("response", on_resp)
    for u in [
        "https://m.ly.com/scenery/searchlist?keyword=%E6%9D%9C%E7%94%AB%E8%8D%89%E5%A0%82",
        "https://m.ly.com/scenery_2/#/pages/search/search?keyword=%E6%9D%9C%E7%94%AB%E8%8D%89%E5%A0%82",
    ]:
        try:
            page.goto(u, timeout=35000, wait_until="domcontentloaded")
            page.wait_for_timeout(8000)
            print("try:", u[-50:], "->", page.url[:80])
        except Exception as e:
            print("err:", str(e)[:80])
    print("xhr:", len(xhrs))
    for x in xhrs[:8]:
        print(x["url"][:130])
        print("  ", x["body"][:200])
    with open(r"C:\Users\28948\Desktop\毕业论文\ai-tourism-agent\script\scrape\captured\tc_m_search_xhr.json", "w", encoding="utf-8") as f:
        json.dump(xhrs, f, ensure_ascii=False, indent=1)
    browser.close()
