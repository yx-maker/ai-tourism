"""探测 12306 余票查询接口（浏览器渲染获取 Cookie 后 API 调用）。"""
import json
from patchright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN", timezone_id="Asia/Shanghai")
    page = ctx.new_page()
    # 先访问 12306 首页拿 Cookie
    page.goto("https://www.12306.cn/index/", timeout=40000, wait_until="domcontentloaded")
    page.wait_for_timeout(8000)
    cookies = ctx.cookies()
    print("cookies:", [c["name"] for c in cookies][:15])

    # 直接 goto API URL（GET 返回 JSON）
    page2 = ctx.new_page()
    resp = page2.goto(
        "https://kyfw.12306.cn/otn/leftTicket/queryG?leftTicketDTO.train_date=2026-10-24&leftTicketDTO.from_station=BBP&leftTicketDTO.to_station=SHH&purpose_codes=ADULT",
        timeout=30000)
    body = resp.text() if resp else ""
    print("status:", resp.status if resp else None, "len:", len(body))
    print("head:", body[:400])
    browser.close()
