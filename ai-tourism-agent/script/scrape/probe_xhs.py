"""探测小红书未登录可见性：搜索页/笔记页是否跳登录墙。"""
import re
from patchright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN", timezone_id="Asia/Shanghai")
    page = ctx.new_page()

    # 1. 搜索页
    try:
        page.goto("https://www.xiaohongshu.com/search_result?keyword=%E6%9D%AD%E5%B7%9E%E6%97%85%E6%B8%B8%E6%94%BB%E7%95%A5",
                  timeout=40000, wait_until="domcontentloaded")
        page.wait_for_timeout(8000)
        print("search url:", page.url[:80])
        body = page.locator("body").inner_text()
        print("body len:", len(body))
        print("login wall:", "登录" in body[:500] or "扫码" in body[:500])
        titles = page.eval_on_selector_all("a[href*='/explore/'], section a.title",
            "els => els.map(e => e.innerText.trim()).filter(t => t).slice(0, 10)")
        print("note titles:", titles[:8])
        with open(r"C:\Users\28948\Desktop\毕业论文\ai-tourism-agent\script\scrape\captured\xhs_search.html", "w", encoding="utf-8") as f:
            f.write(page.content())
    except Exception as e:
        print("search err:", str(e)[:150])

    # 2. 笔记详情页（从搜索结果拿一个 id，或用已知格式）
    try:
        page2 = ctx.new_page()
        page2.goto("https://www.xiaohongshu.com/explore/test123", timeout=30000, wait_until="domcontentloaded")
        page2.wait_for_timeout(5000)
        print("detail url:", page2.url[:80])
    except Exception as e:
        print("detail err:", str(e)[:100])

    browser.close()
