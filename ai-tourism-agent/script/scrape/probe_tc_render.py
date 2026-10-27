"""探测：真浏览器渲染同程北京酒店列表页，验证 DOM 中可提取酒店名+价格。"""
import re
from patchright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN", timezone_id="Asia/Shanghai")
    page = ctx.new_page()
    page.goto("https://www.ly.com/hotel/beijing736/", timeout=45000, wait_until="domcontentloaded")
    page.wait_for_timeout(10000)  # 等 XHR + 渲染
    url = page.url
    print("final url:", url)
    html = page.content()
    print("html len:", len(html))
    # 提取酒店名 + 价格
    names = re.findall(r'class="[^"]*hotelName[^"]*"[^>]*>([^<]{4,40})<', html)
    prices = re.findall(r'[¥￥]\s*(\d{2,5})', html)
    print("酒店名样本:", names[:8])
    print("价格样本:", prices[:15])
    # 也拦截一下 v2/list 响应确认城市
    browser.close()
