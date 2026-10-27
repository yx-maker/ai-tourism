# -*- coding: utf-8 -*-
"""探测小红书登录态下的搜索结果 + 笔记详情结构"""
import json
import time
from pathlib import Path

from patchright.sync_api import sync_playwright

HERE = Path(__file__).parent
STATE = HERE / "captured" / "xhs_state.json"
OUT = HERE / "captured"


def main():
    with sync_playwright() as p:
        # 关键：复用登录捕获时的持久化配置目录（指纹+localStorage+Cookie 完整绑定）
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(HERE / "browser_profile"),
            headless=False,  # 小红书风控识别 headless 指纹，必须真实窗口
            viewport={"width": 1280, "height": 860},
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            args=["--window-position=2000,2000"],  # 窗口挪到屏幕外，减少干扰
        )
        page = ctx.new_page()

        # 1. 搜索页
        page.goto(
            "https://www.xiaohongshu.com/search_result?keyword=%E5%8C%97%E4%BA%AC%20%E6%99%AF%E7%82%B9%20%E6%94%BB%E7%95%A5&source=web_explore_feed",
            timeout=60000, wait_until="domcontentloaded",
        )
        page.wait_for_timeout(5000)
        page.mouse.wheel(0, 1500)  # 触发懒加载
        page.wait_for_timeout(8000)
        print("search url:", page.url[:80])
        print("search title:", page.title())

        cards = page.evaluate(
            """() => {
                const out = [];
                document.querySelectorAll('a[href]').forEach(a => {
                    const href = a.getAttribute('href') || '';
                    if (!/explore|search_result\\//.test(href)) return;
                    const t = a.querySelector('.title, .note-text')?.innerText?.trim()
                           || a.closest('section')?.querySelector('.title, .note-text')?.innerText?.trim()
                           || a.innerText.trim().slice(0, 40);
                    out.push({title: (t || '').slice(0, 50), href: href});
                });
                return out;
            }"""
        )
        print("cards:", len(cards))
        for c in cards[:8]:
            print("  -", c["title"][:35], "|", c["href"][:100])
        # 页面文本采样，判断渲染状态
        sample = page.evaluate("() => document.body.innerText.slice(0, 600)")
        print("body sample:", sample.replace(chr(10), " | ")[:300])

        (OUT / "xhs_search.html").write_text(page.content(), encoding="utf-8")

        # 2. 打开第一个带 token 的笔记详情
        detail = next((c for c in cards if "xsec_token" in c["href"]), None)
        if detail:
            url = "https://www.xiaohongshu.com" + detail["href"] if detail["href"].startswith("/") else detail["href"]
            page.goto(url, timeout=60000, wait_until="domcontentloaded")
            page.wait_for_timeout(6000)
            print("\ndetail title:", page.title())
            info = page.evaluate(
                """() => ({
                    title: document.querySelector('#detail-title, .title')?.innerText?.trim() || null,
                    desc: document.querySelector('#detail-desc, .desc')?.innerText?.trim()?.slice(0, 200) || null,
                    aiBtn: [...document.querySelectorAll('*')].filter(e => /AI\\s*(总结|摘要)/.test(e.innerText || '')).length,
                    bodyLen: document.body.innerText.length,
                })"""
            )
            print("detail:", json.dumps(info, ensure_ascii=False)[:500])
            (OUT / "xhs_note_detail.html").write_text(page.content(), encoding="utf-8")
            # 完整正文文本
            text = page.evaluate("() => document.body.innerText")
            (OUT / "xhs_note_text.txt").write_text(text, encoding="utf-8")
        ctx.close()


if __name__ == "__main__":
    main()
