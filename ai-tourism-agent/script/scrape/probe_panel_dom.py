"""分析城市面板 DOM + 用页面 JS 环境触发切换。"""
import json
from patchright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN", timezone_id="Asia/Shanghai")
    page = ctx.new_page()
    page.goto("https://www.ly.com/scenery/", timeout=40000, wait_until="domcontentloaded")
    page.wait_for_timeout(9000)

    # 页面 JS 环境
    info = page.evaluate("""() => ({
        hasJquery: typeof window.jQuery !== 'undefined',
        jqueryVer: window.jQuery ? window.jQuery.fn.jquery : null,
        citySpanVisible: (() => {
            const els = [...document.querySelectorAll('span.city')];
            return els.map(e => {
                const r = e.getBoundingClientRect();
                return {text: e.innerText.trim(), x: r.x, y: r.y, w: r.width, visible: r.width>0 && r.height>0};
            });
        })(),
        caLCount: document.querySelectorAll('a.ca-l').length,
        cityIdCount: document.querySelectorAll('a[cityid]').length
    })""")
    print(json.dumps(info, ensure_ascii=False, indent=1)[:1500])

    # span.city 的 DOM 上下文
    ctx_html = page.evaluate("""() => {
        const e = document.querySelector('span.city');
        return e ? e.parentElement.outerHTML.slice(0, 500) : null;
    }""")
    print("city span parent:", ctx_html)
    browser.close()
