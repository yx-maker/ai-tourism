"""移动端门票详情页票列表结构探测。"""
import re
from patchright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    iphone = p.devices["iPhone 13"]
    ctx = browser.new_context(**iphone, locale="zh-CN", timezone_id="Asia/Shanghai")
    page = ctx.new_page()
    # 收集 XHR
    xhrs = []
    def on_resp(resp):
        u = resp.url
        if "json" in (resp.headers.get("content-type") or "") and ("ticket" in u.lower() or "sku" in u.lower() or "product" in u.lower() or "price" in u.lower() or "scenery" in u.lower()):
            try:
                b = resp.text()
                if b and len(b) > 100:
                    xhrs.append({"url": u[:180], "len": len(b), "body": b[:1500]})
            except Exception:
                pass
    page.on("response", on_resp)
    page.goto("https://m.ly.com/scenery/scenerydetail_3007.html?refid=18024458", timeout=40000, wait_until="domcontentloaded")
    page.wait_for_timeout(10000)
    print("url:", page.url[:100])
    body = page.locator("body").inner_text()
    print("body len:", len(body))
    prices = re.findall(r"[¥￥]\s*[0-9]{1,5}(?:\.[0-9])?", body)
    print("prices:", prices[:20])
    # 票名
    tickets = re.findall(r"([\u4e00-\u9fa5A-Za-z0-9（）()·]{3,30}票)", body)
    print("ticket names:", list(dict.fromkeys(tickets))[:15])
    with open(r"C:\Users\28948\Desktop\毕业论文\ai-tourism-agent\script\scrape\captured\tc_m_detail.html", "w", encoding="utf-8") as f:
        f.write(page.content())
    with open(r"C:\Users\28948\Desktop\毕业论文\ai-tourism-agent\script\scrape\captured\tc_m_detail_xhr.json", "w", encoding="utf-8") as f:
        import json; json.dump(xhrs, f, ensure_ascii=False, indent=1)
    print("xhr:", [(x["url"][-60:], x["len"]) for x in xhrs[:10]])
    browser.close()
