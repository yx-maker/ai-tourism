# -*- coding: utf-8 -*-
"""12306 余票探测：登录态持久化配置 + 打开查票页拦截 XHR 响应"""
import json
from pathlib import Path

from patchright.sync_api import sync_playwright

HERE = Path(__file__).parent
PROFILE_DIR = HERE / "browser_profile"
OUT = HERE / "captured"

# 查票页 URL：北京→上海，fs/ts 用电报码+城市名
INIT_URL = ("https://kyfw.12306.cn/otn/leftTicket/init?linktypeid=dc"
            "&fs=%E5%8C%97%E4%BA%AC,BJP&ts=%E4%B8%8A%E6%B5%B7,SHH"
            "&date=2026-10-24&flag=N,N")

captured = []


def main():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            viewport=None,
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            args=["--window-position=2000,0", "--no-first-run"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        def on_response(resp):
            url = resp.url
            if "leftTicket/query" in url or "leftTicket/submitOrderRequest" in url:
                try:
                    body = resp.text()
                except Exception:
                    body = ""
                captured.append({"url": url, "status": resp.status, "body": body[:600]})

        page.on("response", on_response)
        page.goto(INIT_URL, timeout=60000, wait_until="domcontentloaded")
        page.wait_for_timeout(15000)

        # 页面渲染出的车次行（DOM 提取兜底）
        rows = page.evaluate(
            """() => {
                const out = [];
                document.querySelectorAll('#queryLeftTable tr').forEach(tr => {
                    const t = tr.innerText.replace(/\\s+/g, ' ').trim();
                    if (t && t.includes('次')) out.push(t.slice(0, 150));
                });
                return out.slice(0, 12);
            }"""
        )
        print("DOM 车次行:", len(rows))
        for r in rows[:6]:
            print("  ", r[:130])

        print("\n捕获 XHR:", len(captured))
        for c in captured[:5]:
            print("  url:", c["url"][:100])
            print("  status:", c["status"], "| body head:", c["body"][:180].replace(chr(10), " "))
            print()

        if captured:
            (OUT / "train12306_xhr.json").write_text(
                json.dumps(captured, ensure_ascii=False, indent=1), encoding="utf-8")
            print("已保存 train12306_xhr.json")
        # 网页完整文本采样
        text = page.evaluate("() => document.body.innerText.slice(0, 400)")
        print("\n页面文本:", text.replace(chr(10), " | ")[:300])
        ctx.close()


if __name__ == "__main__":
    main()
