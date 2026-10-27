# -*- coding: utf-8 -*-
"""探测4：点点 AI 实际对话——发问题→等流式回答完成→提取答案 DOM 结构"""
import json
from pathlib import Path

from patchright.sync_api import sync_playwright

HERE = Path(__file__).parent
OUT = HERE / "captured"


def main():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(HERE / "browser_profile"),
            headless=False, viewport=None,
            locale="zh-CN", timezone_id="Asia/Shanghai",
            args=["--window-position=2000,0", "--no-first-run"])
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://www.xiaohongshu.com/ai_chat?from=sidebar", timeout=60000,
                  wait_until="domcontentloaded")
        page.wait_for_timeout(6000)

        # 主输入框：取「可见且已绑定事件」的那个（页面有 aria-hidden 的复制品会拦截点击）
        ta = page.locator('textarea[name="aiSearchTextarea"][data-hp-bound="1"]').first
        if ta.count() == 0:
            ta = page.locator("textarea:visible").last
        ta.click()
        ta.type("北京一日游，必去的景点和特色美食，帮我规划路线", delay=60)
        page.keyboard.press("Enter")
        print("已发送，等待回答……")

        # 轮询等待回答稳定（流式输出，连续 6 秒长度不变视为完成）
        last_len, stable = -1, 0
        for _ in range(40):
            page.wait_for_timeout(2000)
            cur = page.evaluate(
                """() => {
                    const body = document.body.innerText;
                    // 回答区一般在问题之后；粗略取全文长度判断稳定
                    return body.length;
                }"""
            )
            if cur == last_len:
                stable += 1
                if stable >= 3:
                    break
            else:
                stable = 0
            last_len = cur
        print("回答流式完成")

        # 提取消息结构
        msgs = page.evaluate(
            """() => {
                const out = [];
                document.querySelectorAll('[class*=message], [class*=bubble], [class*=answer], [class*=md], [class*=markdown]').forEach(e => {
                    const t = (e.innerText || '').trim();
                    if (t && t.length > 30) out.push({cls: String(e.className).slice(0, 70), len: t.length,
                                                       head: t.slice(0, 120)});
                });
                return out.slice(0, 10);
            }"""
        )
        print(json.dumps(msgs, ensure_ascii=False, indent=1)[:1200])
        text = page.evaluate("() => document.body.innerText")
        (OUT / "xhs_diandian_answer.txt").write_text(text, encoding="utf-8")
        (OUT / "xhs_ai_chat_conv.html").write_text(page.content(), encoding="utf-8")
        print("\n全文已存 captured/xhs_diandian_answer.txt，长度:", len(text))
        ctx.close()


if __name__ == "__main__":
    main()
