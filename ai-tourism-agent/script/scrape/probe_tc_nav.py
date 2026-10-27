"""从同程首页搜索北京酒店，找到真实城市列表页 URL。"""
import re
from patchright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN", timezone_id="Asia/Shanghai")
    page = ctx.new_page()
    page.goto("https://www.ly.com/hotel/", timeout=45000, wait_until="domcontentloaded")
    page.wait_for_timeout(6000)
    # 找搜索框（可能是 input placeholder 含 城市/目的地）
    inputs = page.locator("input").all()
    for i, inp in enumerate(inputs[:15]):
        ph = inp.get_attribute("placeholder") or ""
        if ph:
            print(f"input[{i}] placeholder: {ph[:30]}")
    # 尝试热门城市链接
    links = page.locator("a").all()
    bj = [l for l in links if (l.text_content() or "").strip() in ("北京", "北京酒店")]
    print("北京链接数:", len(bj))
    if bj:
        href = bj[0].get_attribute("href")
        print("北京链接:", href)
    browser.close()
