"""探测同程火车票列表页（浏览器渲染）。"""
import re
from patchright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN", timezone_id="Asia/Shanghai")
    page = ctx.new_page()
    # 火车票查询页（北京→上海）
    page.goto("https://www.ly.com/train/list?from=%E5%8C%97%E4%BA%AC&to=%E4%B8%8A%E6%B5%B7&date=2026-10-24",
              timeout=40000, wait_until="domcontentloaded")
    page.wait_for_timeout(12000)
    print("url:", page.url[:100])
    body = page.locator("body").inner_text()
    print("body len:", len(body))
    prices = re.findall(r"[¥￥]\s*[0-9]{1,4}(?:\.[0-9])?", body)
    print("prices:", prices[:20])
    # 车次
    trains = re.findall(r"\b(G[0-9]{1,4}|D[0-9]{1,4}|C[0-9]{1,4}|K[0-9]{1,4}|T[0-9]{1,3}|Z[0-9]{1,3})\b", body)
    print("trains:", list(dict.fromkeys(trains))[:20])
    with open(r"C:\Users\28948\Desktop\毕业论文\ai-tourism-agent\script\scrape\captured\tc_train.html", "w", encoding="utf-8") as f:
        f.write(page.content())
    browser.close()
