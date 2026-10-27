"""访问移动端详情页，解析 getAllResourceOutWithMerger 的票品清单。"""
import json, re
from patchright.sync_api import sync_playwright

TARGETS = [("3007", "故宫"), ("3023", "颐和园"), ("3518", "什刹海")]

def parse_products(body: str):
    try:
        data = json.loads(body)
        items = data["Body"]["itemList"]
    except Exception as e:
        return [], str(e)[:80]
    out = []
    for bar in items:
        for typ in bar.get("productTypeInfoList", []) or []:
            for prod in typ.get("products", []) or []:
                out.append({
                    "name": prod.get("productName"),
                    "crowd": prod.get("targetingCrowdName"),
                    "price": prod.get("lowestAmount"),
                    "advance": prod.get("lowestAmountAdvance"),
                })
    return out, None

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    iphone = p.devices["iPhone 13"]
    ctx = browser.new_context(**iphone, locale="zh-CN", timezone_id="Asia/Shanghai")
    for sid, name in TARGETS:
        page = ctx.new_page()
        captured = {"body": None}
        def on_resp(resp, captured=captured):
            if "getAllResourceOutWithMerger" in resp.url:
                try:
                    captured["body"] = resp.text()
                except Exception:
                    pass
        page.on("response", on_resp)
        page.goto(f"https://m.ly.com/scenery/scenerydetail_{sid}.html?refid=18024458",
                  timeout=40000, wait_until="domcontentloaded")
        page.wait_for_timeout(9000)
        if captured["body"]:
            prods, err = parse_products(captured["body"])
            print(f"== {name} #{sid}: {len(prods)} 票品")
            for pr in prods[:12]:
                print(f"   {pr['price']:>6} | {str(pr['name'])[:40]} | {pr['crowd']}")
        else:
            print(f"== {name} #{sid}: 未捕获 API")
        page.close()
        import time; time.sleep(2)
    browser.close()
