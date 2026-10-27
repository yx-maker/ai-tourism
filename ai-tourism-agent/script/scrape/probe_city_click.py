"""点击 a.ca-l 北京 → 拿城市门票列表页 URL 和卡片结构。"""
import re
from patchright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN", timezone_id="Asia/Shanghai")
    page = ctx.new_page()
    page.goto("https://www.ly.com/scenery/", timeout=35000, wait_until="domcontentloaded")
    page.wait_for_timeout(9000)
    try:
        page.locator("a.ca-l", has_text="北京").first.click(timeout=6000)
        page.wait_for_timeout(8000)
        print("FINAL URL:", page.url[:140])
        body = page.locator("body").inner_text()
        print("body len:", len(body))
        prices = re.findall(r"[¥￥]\s*[0-9]{1,5}(?:\.[0-9])?(?:起)?", body)
        print("prices:", prices[:15])
        html = page.content()
        with open(r"C:\Users\28948\Desktop\毕业论文\ai-tourism-agent\script\scrape\captured\tc_scenery_city.html", "w", encoding="utf-8") as f:
            f.write(html)
        # 卡片结构样例
        m = re.search(r'BookSceneryTicket_\d+\.html', html)
        print("has ticket links:", bool(m))
        if m:
            i = m.start()
            print(html[i-400:i+600].replace(chr(10), ' ')[:800])
    except Exception as e:
        print("err:", str(e)[:250])
    browser.close()
