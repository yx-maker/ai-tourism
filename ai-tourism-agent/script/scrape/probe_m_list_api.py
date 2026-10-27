"""探测移动端城市门票搜索列表页 API。"""
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
        if "json" in (resp.headers.get("content-type") or "") and len(u) > 60:
            try:
                b = resp.text()
                if b and len(b) > 200:
                    xhrs.append({"url": u[:250], "len": len(b), "body": b[:2000]})
            except Exception:
                pass
    page.on("response", on_resp)
    page.goto("https://m.ly.com/scenery_2/#/pages/list/list?cityId=324&keyword=%E6%9D%9C%E7%94%AB%E8%8D%89%E5%A0%82&refid=2000411121",
              timeout=40000, wait_until="domcontentloaded")
    page.wait_for_timeout(12000)
    print("url:", page.url[:100])
    body = page.locator("body").inner_text()
    print("body len:", len(body))
    import re
    print("prices:", re.findall(r"[¥￥]\s*[0-9]{1,5}(?:\.[0-9])?", body)[:15])
    print("--- xhr:")
    for x in xhrs:
        print(x["url"][:160])
        print("   body head:", x["body"][:180].replace(chr(10), " "))
    with open(r"C:\Users\28948\Desktop\毕业论文\ai-tourism-agent\script\scrape\captured\tc_m_list_api.json", "w", encoding="utf-8") as f:
        json.dump(xhrs, f, ensure_ascii=False, indent=1)
    browser.close()
