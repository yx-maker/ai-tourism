# -*- coding: utf-8 -*-
"""探测小红书搜索页 AI 总结卡（多查询、多等待策略）"""
import json
from pathlib import Path

from patchright.sync_api import sync_playwright

HERE = Path(__file__).parent
OUT = HERE / "captured"

QUERIES = ["北京景点推荐", "北京美食推荐"]


def main():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(HERE / "browser_profile"),
            headless=False, viewport=None,
            locale="zh-CN", timezone_id="Asia/Shanghai",
            args=["--window-position=2000,0", "--no-first-run"])
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        # 拦截 AI 相关 XHR（AI 总结通常走独立接口）
        ai_xhr = []
        def on_response(resp):
            u = resp.url
            if any(k in u.lower() for k in ["ai", "summary", "intelligent", "searchx", "diandian"]):
                try:
                    body = resp.text()
                except Exception:
                    body = ""
                if len(body) > 50:
                    ai_xhr.append({"url": u[:160], "len": len(body), "head": body[:300]})
        page.on("response", on_response)

        for kw in QUERIES:
            print(f"\n===== {kw} =====")
            page.goto(
                f"https://www.xiaohongshu.com/search_result?keyword={kw}&source=web_explore_feed",
                timeout=60000, wait_until="domcontentloaded")
            page.wait_for_timeout(6000)
            # AI 总结可能延迟出现，多等几轮
            found = None
            for i in range(5):
                page.wait_for_timeout(2000)
                found = page.evaluate(
                    """() => {
                        // 找包含 AI 总结/智能总结 的容器
                        const all = [...document.querySelectorAll('div, section')];
                        for (const el of all) {
                            const cls = el.className || '';
                            if (typeof cls === 'string' && /ai[-_]?(summary|card|answer)/i.test(cls)) {
                                return {type: 'class', cls: cls.slice(0, 80),
                                        text: el.innerText.slice(0, 400)};
                            }
                        }
                        const body = document.body.innerText;
                        const idx = body.indexOf('AI总结') >= 0 ? body.indexOf('AI总结')
                                 : body.indexOf('AI 总结') >= 0 ? body.indexOf('AI 总结')
                                 : body.indexOf('智能总结') >= 0 ? body.indexOf('智能总结') : -1;
                        if (idx >= 0) {
                            return {type: 'text', pos: idx, text: body.slice(idx, idx + 400)};
                        }
                        return null;
                    }"""
                )
                if found:
                    break
            print("AI总结卡:", json.dumps(found, ensure_ascii=False)[:500] if found else "未出现")

        print("\n===== AI 相关 XHR =====")
        for x in ai_xhr[:6]:
            print(" ", x["url"])
            print("   len:", x["len"], "| head:", x["head"][:200].replace(chr(10), " "))

        if ai_xhr:
            (OUT / "xhs_ai_xhr.json").write_text(json.dumps(ai_xhr, ensure_ascii=False, indent=1), encoding="utf-8")
        ctx.close()


if __name__ == "__main__":
    main()
