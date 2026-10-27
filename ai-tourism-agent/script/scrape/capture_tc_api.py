"""用真浏览器打开同程酒店列表页，拦截 tapi 请求的真实参数与响应。"""
import json
import sys
from pathlib import Path

from patchright.sync_api import sync_playwright

OUT = Path(__file__).parent / "captured"
OUT.mkdir(exist_ok=True)

captured = []

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            viewport={"width": 1440, "height": 900},
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
        )
        page = ctx.new_page()

        def on_response(resp):
            url = resp.url
            if "tapi" in url or ("api" in url and "ly.com" in url):
                try:
                    body = resp.text()[:20000]
                except Exception:
                    body = "<binary>"
                req = resp.request
                try:
                    post = req.post_data[:8000] if req.post_data else ""
                except Exception:
                    post = ""
                captured.append({
                    "url": url,
                    "method": req.method,
                    "status": resp.status,
                    "post_data": post,
                    "response_head": body[:3000],
                })

        page.on("response", on_response)
        try:
            page.goto("https://www.ly.com/hotel/beijing736/", timeout=45000, wait_until="domcontentloaded")
            page.wait_for_timeout(9000)  # 等 XHR 完成
        except Exception as e:
            print("nav error:", e)

        browser.close()

    with open(OUT / "tc_api_capture.json", "w", encoding="utf-8") as f:
        json.dump(captured, f, ensure_ascii=False, indent=1)
    print(f"captured {len(captured)} api calls")
    for c in captured:
        print("-", c["method"], c["status"], c["url"][:100])

if __name__ == "__main__":
    main()
