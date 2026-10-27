# -*- coding: utf-8 -*-
"""探测2：笔记详情页 AI 总结 + 点点 AI 入口"""
import json
from pathlib import Path

from patchright.sync_api import sync_playwright

HERE = Path(__file__).parent
OUT = HERE / "captured"
STATE = OUT / "xhs_state.json"


def main():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(HERE / "browser_profile"),
            headless=False, viewport=None,
            locale="zh-CN", timezone_id="Asia/Shanghai",
            args=["--window-position=2000,0", "--no-first-run"])
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        # 1. 首页找「点点」入口链接
        page.goto("https://www.xiaohongshu.com/", timeout=60000, wait_until="domcontentloaded")
        page.wait_for_timeout(4000)
        links = page.evaluate(
            """() => [...document.querySelectorAll('a')].map(a => ({
                    text: a.innerText.trim(), href: a.href }))
                    .filter(x => /点点|ai|Ai|AI/.test(x.text) && x.text.length < 10)
                    .slice(0, 8)"""
        )
        print("AI 相关入口:", json.dumps(links, ensure_ascii=False))

        # 2. 高赞笔记详情找 AI 总结（济南 3937 赞那篇 id 从 xhs_notes.json 取）
        notes = json.loads((OUT / "xhs_notes.json").read_text(encoding="utf-8"))
        # 找点赞数最高的一篇
        def like_num(s):
            s = (s or "").replace("万", "0000")
            try:
                return float(s.replace("赞", "")) if s and any(c.isdigit() for c in s) else 0
            except Exception:
                return 0
        best = max(notes, key=lambda n: like_num(n.get("likes", "")))
        print("\n打开高赞笔记:", best["title"][:30], "👍", best["likes"])
        page.goto(best["url"], timeout=60000, wait_until="domcontentloaded")
        page.wait_for_timeout(6000)
        info = page.evaluate(
            """() => {
                const body = document.body.innerText;
                const markers = ['AI总结', 'AI 总结', '笔记总结', '智能总结', 'AI摘要', '摘要'];
                const hits = {};
                for (const m of markers) {
                    const i = body.indexOf(m);
                    if (i >= 0) hits[m] = body.slice(i, i + 300);
                }
                // 找展开按钮类元素
                const btns = [...document.querySelectorAll('[class*=summary], [class*=Summary], [class*=ai], button, span')]
                    .filter(e => e.innerText && /AI\\s*总结|查看总结|笔记总结/.test(e.innerText))
                    .map(e => ({tag: e.tagName, cls: String(e.className).slice(0, 60), text: e.innerText.trim().slice(0, 30)}))
                    .slice(0, 5);
                return {hits, btns, len: body.length};
            }"""
        )
        print(json.dumps(info, ensure_ascii=False)[:800])
        (OUT / "xhs_note_ai_probe.html").write_text(page.content(), encoding="utf-8")
        ctx.close()


if __name__ == "__main__":
    main()
