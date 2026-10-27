"""分析故宫/颐和园详情页票种 SKU 结构。"""
import re
from patchright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN", timezone_id="Asia/Shanghai")
    page = ctx.new_page()
    for sid, name in [("3007", "故宫"), ("3023", "颐和园"), ("3518", "什刹海")]:
        page.goto(f"https://www.ly.com/scenery/BookSceneryTicket_{sid}.html", timeout=35000, wait_until="domcontentloaded")
        page.wait_for_timeout(5000)
        html = page.content()
        with open(rf"C:\Users\28948\Desktop\毕业论文\ai-tourism-agent\script\scrape\captured\tc_sku_{sid}.html", "w", encoding="utf-8") as f:
            f.write(html)
        # 票种列表：找「成人票」等关键词附近的价格
        rows = re.findall(r'((?:成人|大|普通)?票)[^¥￥]{0,200}[¥￥]\s*([0-9]{1,4}(?:\.[0-9])?)', html[:200000])
        print(f"== {name} #{sid}")
        # 商品名+价格对（更通用）
        items = re.findall(r'([\u4e00-\u9fa5A-Za-z0-9（）()·]{4,40}(?:票|预约))[^¥￥]{0,120}?[¥￥]\s*<b>([0-9.]+)</b>', html)
        print(" sku:", items[:8])
        # 也找非 b 标签的
        items2 = re.findall(r'(?:title|data-title)="([^"]{4,40}票[^"]{0,20})"[^¥￥]{0,300}?[¥￥]\s*([0-9.]{1,6})', html)
        print(" attr:", items2[:8])
        # s_p_t 头价
        head = re.search(r's_p_t[^>]*>\s*<span>¥<b>([0-9.]+)</b>', html)
        print(" head:", head.group(1) if head else None)
    browser.close()
