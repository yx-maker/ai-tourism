"""JS 强制点击城市链接，观察跳转 URL。"""
import re
from patchright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN", timezone_id="Asia/Shanghai")
    page = ctx.new_page()
    page.goto("https://www.ly.com/scenery/", timeout=35000, wait_until="domcontentloaded")
    page.wait_for_timeout(9000)
    # dump 面板里所有城市 mid
    mids = page.eval_on_selector_all("a.ca-l", "els => els.map(e => e.getAttribute('mid') + '=' + e.innerText.trim())")
    print("cities:", mids[:30])
    # JS 点击北京
    try:
        page.evaluate("""
            const links = [...document.querySelectorAll('a.ca-l')];
            const bj = links.find(a => a.innerText.trim() === '北京');
            bj.click();
        """)
        page.wait_for_timeout(9000)
        print("URL AFTER:", page.url[:150])
        body = page.locator("body").inner_text()
        prices = re.findall(r"[¥￥]\s*[0-9]{1,5}(?:\.[0-9])?(?:起)?", body)
        print("body len:", len(body), "| prices:", prices[:10])
        with open(r"C:\Users\28948\Desktop\毕业论文\ai-tourism-agent\script\scrape\captured\tc_scenery_bj3.html", "w", encoding="utf-8") as f:
            f.write(page.content())
    except Exception as e:
        print("err:", str(e)[:200])
    browser.close()
