"""交互探测：门票首页城市切换 → 北京列表页。"""
import re
from patchright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN", timezone_id="Asia/Shanghai")
    page = ctx.new_page()
    page.goto("https://www.ly.com/scenery/", timeout=35000, wait_until="domcontentloaded")
    page.wait_for_timeout(9000)

    # 找城市切换入口：页面上有"当前："文本
    candidates = page.locator("text=/当前|苏州|北京/")
    n = candidates.count()
    print("city-ish locators:", n)
    for i in range(min(n, 8)):
        el = candidates.nth(i)
        try:
            txt = el.inner_text()[:30]
            tag = el.evaluate("e => e.tagName + '.' + (e.className||'')")
            print(f"  [{i}] <{tag}> {txt!r}")
        except Exception:
            pass

    # 尝试点击第一个（城市tab）
    try:
        candidates.first.click(timeout=4000)
        page.wait_for_timeout(2500)
        # 展开后再找"北京"
        bj = page.locator("text=北京").first
        bj.click(timeout=4000)
        page.wait_for_timeout(7000)
        print("FINAL URL:", page.url[:140])
        body = page.locator("body").inner_text()
        prices = re.findall(r"[¥￥]\s*[0-9]{1,5}(?:\.[0-9])?(?:起)?", body)
        print("prices:", prices[:12])
        print("body len:", len(body))
        with open(r"C:\Users\28948\Desktop\毕业论文\ai-tourism-agent\script\scrape\captured\tc_scenery_bj2.html", "w", encoding="utf-8") as f:
            f.write(page.content())
    except Exception as e:
        print("flow err:", str(e)[:200])
    browser.close()
