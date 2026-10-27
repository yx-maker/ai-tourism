# -*- coding: utf-8 -*-
"""探测3：点点 AI 对话页（ai_chat）交互与响应结构"""
import json
from pathlib import Path

from patchright.sync_api import sync_playwright

HERE = Path(__file__).parent
OUT = HERE / "captured"

ai_responses = []


def main():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(HERE / "browser_profile"),
            headless=False, viewport=None,
            locale="zh-CN", timezone_id="Asia/Shanghai",
            args=["--window-position=2000,0", "--no-first-run"])
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        def on_response(resp):
            u = resp.url
            if any(k in u.lower() for k in ["chat", "completion", "stream", "conversation", "aigc"]):
                try:
                    body = resp.text()
                except Exception:
                    body = ""
                ai_responses.append({"url": u[:180], "status": resp.status, "len": len(body),
                                     "head": body[:400]})

        page.on("response", on_response)
        page.goto("https://www.xiaohongshu.com/ai_chat?from=sidebar", timeout=60000,
                  wait_until="domcontentloaded")
        page.wait_for_timeout(8000)
        print("url:", page.url[:90])
        print("title:", page.title())

        # 页面结构：输入框 + 推荐问题
        info = page.evaluate(
            """() => {
                const inputs = [...document.querySelectorAll('textarea, input, [contenteditable=true]')]
                    .map(e => ({tag: e.tagName, cls: String(e.className).slice(0, 60),
                                ph: e.placeholder || e.getAttribute('data-placeholder') || ''}));
                const sugg = [...document.querySelectorAll('[class*=suggest] [class*=item], [class*=recommend]')]
                    .map(e => e.innerText.trim().slice(0, 40)).filter(t => t && t.length > 3).slice(0, 8);
                return {inputs, sugg, bodyLen: document.body.innerText.length,
                        sample: document.body.innerText.slice(0, 300)};
            }"""
        )
        print(json.dumps(info, ensure_ascii=False, indent=1)[:900])

        # 尝试发送一条消息
        sent = page.evaluate(
            """() => {
                const ta = document.querySelector('textarea') ||
                           document.querySelector('[contenteditable=true]');
                if (!ta) return 'NO_INPUT';
                return 'FOUND: ' + ta.tagName + ' | cls=' + String(ta.className).slice(0, 50);
            }"""
        )
        print("\n输入框:", sent)

        (OUT / "xhs_ai_chat_page.html").write_text(page.content(), encoding="utf-8")
        ctx.close()

    print("\n===== AI 对话相关 XHR =====")
    for x in ai_responses[:8]:
        print(" ", x["url"])
        print("  status:", x["status"], "len:", x["len"])
    if ai_responses:
        (OUT / "xhs_ai_chat_xhr.json").write_text(json.dumps(ai_responses, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
