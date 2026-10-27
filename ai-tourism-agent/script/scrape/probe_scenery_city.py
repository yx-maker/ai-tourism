"""点击城市切换器选北京，拿到城市门票列表 URL 和卡片结构。"""
import re
from patchright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN", timezone_id="Asia/Shanghai")
    page = ctx.new_page()
    page.goto("https://www.ly.com/scenery/", timeout=35000, wait_until="domcontentloaded")
    page.wait_for_timeout(6000)
    # 点击城市 tab（先试文本=北京）
    try:
        page.locator("text=北京").first.click(timeout=5000)
        page.wait_for_timeout(7000)
        print("after click url:", page.url[:130])
    except Exception as e:
        print("click err:", str(e)[:120])
        # 试试 hover 展开城市面板
        try:
            page.locator("text=切换城市, [class*=city]").first.hover(timeout=3000)
            page.wait_for_timeout(2000)
            page.locator("text=北京").first.click(timeout=4000)
            page.wait_for_timeout(7000)
            print("after hover+click url:", page.url[:130])
        except Exception as e2:
            print("hover err:", str(e2)[:120])
    # dump 当前页面卡片
    html = page.content()
    with open(r"C:\Users\28948\Desktop\毕业论文\ai-tourism-agent\script\scrape\captured\tc_scenery_bj.html", "w", encoding="utf-8") as f:
        f.write(html)
    body = page.locator("body").inner_text()
    prices = re.findall(r"[¥￥]\s*[0-9]{1,5}(?:\.[0-9])?(?:起)?", body)
    names = re.findall(r"([\u4e00-\u9fa5]{3,15}(?:公园|博物馆|长城|古镇|景区|乐园|寺庙|宫|园|湖|山))", body)
    print("prices:", prices[:15])
    print("names:", list(dict.fromkeys(names))[:20])
    browser.close()
