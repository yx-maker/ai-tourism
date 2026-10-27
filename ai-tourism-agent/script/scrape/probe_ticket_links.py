"""探测同程门票：首页链接结构 + 城市列表页。"""
import re
from patchright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN", timezone_id="Asia/Shanghai")
    page = ctx.new_page()
    page.goto("https://www.ly.com/scenery/", timeout=35000, wait_until="domcontentloaded")
    page.wait_for_timeout(7000)
    # dump 所有含 scenery 的链接
    links = page.eval_on_selector_all("a", "els => els.map(e => e.getAttribute('href') + ' || ' + (e.innerText||'').trim().slice(0,20)).filter(t => t.includes('scenery'))")
    seen = set()
    for l in links[:60]:
        if l not in seen:
            seen.add(l)
            print(l[:140])
    browser.close()
