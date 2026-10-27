"""dump 门票首页全部链接，找城市列表入口。"""
from patchright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN", timezone_id="Asia/Shanghai")
    page = ctx.new_page()
    page.goto("https://www.ly.com/scenery/", timeout=35000, wait_until="domcontentloaded")
    page.wait_for_timeout(8000)
    links = page.eval_on_selector_all(
        "a[href]",
        "els => els.map(e => e.getAttribute('href') + ' ||| ' + (e.innerText||'').trim().replace(/\\n/g,' ').slice(0,25))")
    seen = set()
    for l in links:
        key = l.split(" ||| ")[0]
        if key in seen:
            continue
        seen.add(key)
        # 只打印含城市名或非常规的
        if any(k in l for k in ("北京", "上海", "城市", "city", "City", "热门")) or (
                l.startswith("/") and "zhuanti" not in l and "BookSceneryTicket" not in l and "scenery/" not in l):
            print(l[:130])
    print("=== total unique:", len(seen))
    # 打印页面上的城市切换组件文本
    try:
        txt = page.locator("body").inner_text()[:600]
        print("HEAD TEXT:", txt.replace("\n", " | ")[:500])
    except Exception:
        pass
    browser.close()
