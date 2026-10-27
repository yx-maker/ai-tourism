# -*- coding: utf-8 -*-
"""12306 免登录查票：打开查票页 → 点击查询 → 拦截 XHR + DOM 提取"""
import json
from pathlib import Path

from patchright.sync_api import sync_playwright

HERE = Path(__file__).parent
PROFILE_DIR = HERE / "browser_profile"
OUT = HERE / "captured"

INIT_URL = ("https://kyfw.12306.cn/otn/leftTicket/init?linktypeid=dc"
            "&fs=%E5%8C%97%E4%BA%AC,BJP&ts=%E4%B8%8A%E6%B5%B7,SHH"
            "&date=2026-10-25&flag=N,N")

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
            if "leftTicket/query" in resp.url and "init" not in resp.url:
                try:
                    body = resp.text()
                except Exception:
                    body = ""
                captured.append({"url": resp.url, "status": resp.status, "body": body[:3000]})

        page.on("response", on_response)
        page.goto(INIT_URL, timeout=60000, wait_until="domcontentloaded")
        page.wait_for_timeout(6000)

        # 点击查询按钮
        try:
            page.click("#query_ticket", timeout=5000)
            print("已点击查询按钮")
        except Exception as e:
            print("点击查询失败:", str(e)[:80])
        page.wait_for_timeout(10000)

        rows = page.evaluate(
            """() => {
                const out = [];
                document.querySelectorAll('#queryLeftTable tr').forEach(tr => {
                    const t = tr.innerText.replace(/\\s+/g, ' ').trim();
                    if (t && /次|G|D|C|K|T|Z/.test(t)) out.push(t.slice(0, 160));
                });
                return out.slice(0, 10);
            }"""
        )
        print("DOM 车次行:", len(rows))
        for r in rows[:8]:
            print("  ", r[:150])

        print("\n捕获 XHR:", len(captured))
        for c in captured[:3]:
            print("  url:", c["url"][:110])
            print("  status:", c["status"], "| body head:", c["body"][:250].replace(chr(10), " "))

        if captured:
            (OUT / "train12306_xhr.json").write_text(
                json.dumps(captured, ensure_ascii=False, indent=1), encoding="utf-8")
            print("\n已保存 train12306_xhr.json")
        ctx.close()


if __name__ == "__main__":
    main()
