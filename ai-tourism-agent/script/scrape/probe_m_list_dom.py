"""解析移动端城市搜索列表页的卡片结构（名称+价格+sid）。"""
import json, re
from patchright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    iphone = p.devices["iPhone 13"]
    ctx = browser.new_context(**iphone, locale="zh-CN", timezone_id="Asia/Shanghai")
    page = ctx.new_page()
    page.goto("https://m.ly.com/scenery_2/#/pages/list/list?cityId=324&keyword=%E6%9D%9C%E7%94%AB%E8%8D%89%E5%A0%82&refid=2000411121",
              timeout=40000, wait_until="domcontentloaded")
    page.wait_for_timeout(12000)
    html = page.content()
    with open(r"C:\Users\28948\Desktop\毕业论文\ai-tourism-agent\script\scrape\captured\tc_m_list_kw.html", "w", encoding="utf-8") as f:
        f.write(html)
    # 通用卡片提取：尝试常见选择器
    info = page.evaluate("""() => {
        // 找含 ¥ 的元素及兄弟文本
        const out = [];
        document.querySelectorAll('div,li,a,section').forEach(el => {
            const t = el.innerText || '';
            if (t.includes('¥') && t.length < 200 && el.children.length >= 1 && !out.some(o => el.contains(document.querySelector('*')) )) {}
        });
        return null;
    }""")
    # 直接正则 HTML
    cards = re.findall(r'scenerydetail_(\d+)\.html', html)
    print("detail ids:", list(dict.fromkeys(cards))[:20])
    # 找杜甫草堂卡片上下文
    i = html.find('杜甫草堂')
    print(html[max(0,i-600):i+900].replace(chr(10),' ')[:1200])
    browser.close()
