"""验证移动端城市全量列表页：滚动加载 + 卡片解析。"""
import re, time
from patchright.sync_api import sync_playwright

def parse_cards(page):
    """按 resourseBox 卡片解析文本流。"""
    return page.evaluate("""() => {
        const cards = [];
        document.querySelectorAll('.resourseBox').forEach(box => {
            const texts = [];
            box.querySelectorAll('taro-text-core, .txt, .price').forEach(t => {
                const v = (t.innerText || '').trim();
                if (v) texts.push(v);
            });
            if (texts.length) cards.push(texts);
        });
        return cards;
    }""")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    iphone = p.devices["iPhone 13"]
    ctx = browser.new_context(**iphone, locale="zh-CN", timezone_id="Asia/Shanghai")
    page = ctx.new_page()
    page.goto("https://m.ly.com/scenery_2/#/pages/list/list?cityId=324&refid=2000411121",
              timeout=40000, wait_until="domcontentloaded")
    page.wait_for_timeout(12000)
    cards = parse_cards(page)
    print("initial cards:", len(cards))
    for c in cards[:8]:
        print("  ", c[:8])
    # 滚动加载
    for i in range(5):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(2500)
    cards = parse_cards(page)
    print("after scroll cards:", len(cards))
    for c in cards[:20]:
        print("  ", c[:8])
    browser.close()
