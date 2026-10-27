# -*- coding: utf-8 -*-
"""探测：用渲染浏览器能否从 OTA 拿到真实酒店/门票价格（一次性探针，非生产脚本）。"""
import re
from pathlib import Path

from patchright.sync_api import sync_playwright

PROFILE = Path(__file__).parent / "ota_profile"
TARGETS = [
    ("携程门票-故宫", "https://piao.ctrip.com/dest/t1-beijing-1.html"),
    ("同程门票", "https://piao.ly.com/"),
    ("去哪儿门票", "https://piao.qunar.com/"),
    ("携程门票搜索页", "https://piao.ctrip.com/ticket/list?keyword=%E6%95%85%E5%AE%AB"),
]

PRICE_RE = re.compile(r"[¥￥]\s?(\d{2,5})")

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE), headless=False, viewport=None,
        locale="zh-CN", timezone_id="Asia/Shanghai",
        args=["--start-maximized", "--window-position=2000,0", "--no-first-run"])
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    for name, url in TARGETS:
        try:
            page.goto(url, timeout=45000, wait_until="domcontentloaded")
            page.wait_for_timeout(7000)
            txt = page.evaluate("() => document.body.innerText")
            prices = PRICE_RE.findall(txt)
            print(f"{name}: 文本 {len(txt)} 字 | 价格 {prices[:12]}")
            print("   前100字:", txt[:100].replace("\n", " "))
        except Exception as e:
            print(f"{name}: ERR {type(e).__name__} {str(e)[:100]}")
        print("-" * 60)
    ctx.close()
