# -*- coding: utf-8 -*-
"""
点点 AI（小红书站内助手）城市问答爬虫
每城两问：① 一日游路线规划（景点+时间轴+交通）② 特色美食推荐
回答为 markdown 块流式输出，稳定后按 .markdown-block 提取。

用法：
    python scrape_diandian.py                # 15 城全量（约 20 分钟）
    python scrape_diandian.py --cities 北京   # 指定城市
"""
import argparse
import json
import random
import time
from pathlib import Path

from patchright.sync_api import sync_playwright

HERE = Path(__file__).parent
OUT_FILE = HERE / "captured" / "xhs_diandian.json"

CITIES = ["北京", "上海", "广州", "深圳", "成都", "杭州", "武汉", "长沙",
          "西安", "重庆", "厦门", "三亚", "桂林", "丽江", "济南"]

Q_ROUTE = "{city}一日游路线规划：必去景点按时间顺序串联，含交通衔接、门票预约提醒和顺路美食"
Q_FOOD = "{city}特色美食推荐：本地人常去的老字号和小吃店，按区域汇总并标注人均消费"


def load_result() -> dict:
    if OUT_FILE.exists():
        return json.loads(OUT_FILE.read_text(encoding="utf-8"))
    return {}


def save_result(r: dict):
    OUT_FILE.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")


def ask_and_extract(page, question: str, max_wait_s: int = 150) -> str:
    """发问→轮询直到回答充实且稳定→全文切片提取（含思考阶段容忍）"""
    ta = page.locator('textarea[name="aiSearchTextarea"][data-hp-bound="1"]').first
    if ta.count() == 0:
        ta = page.locator("textarea:visible").last
    ta.click()
    ta.type(question, delay=40)
    page.keyboard.press("Enter")

    JS_EXTRACT = """(q) => {
        const body = document.body.innerText;
        // 优先完整问题匹配；回退到 20 字前缀
        let qi = body.lastIndexOf(q);
        let skip = qi >= 0 ? q.length : 20;
        if (qi < 0) { qi = body.lastIndexOf(q.slice(0, 20)); }
        if (qi < 0) return '';
        let seg = body.slice(qi + skip);
        for (const marker of ['猜你想问', '相关搜索', '继续问', '内容由AI生成，请注意核实']) {
            const i = seg.indexOf(marker);
            if (i > 150) seg = seg.slice(0, i);
        }
        return seg.trim();
    }"""

    def extract() -> str:
        return page.evaluate(JS_EXTRACT, question)

    last_len, stable = -1, 0
    waited = 0
    while waited < max_wait_s * 1000:
        page.wait_for_timeout(3000)
        waited += 3000
        cur = extract()
        if len(cur) >= 300 and cur == last_len:
            stable += 1
            if stable >= 2:  # 内容充实且 6 秒无变化
                return cur
        else:
            stable = 0
        last_len = cur
    return extract()  # 超时也返回当前内容，由调用方判断长度


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cities", nargs="*", default=CITIES)
    args = ap.parse_args()

    result = load_result()
    print(f"已有 {len(result)} 条问答记录，续抓模式")

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(HERE / "browser_profile"),
            headless=False, viewport=None,
            locale="zh-CN", timezone_id="Asia/Shanghai",
            args=["--start-maximized", "--window-position=2000,0", "--no-first-run"])
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        for city in args.cities:
            for kind, qtpl in [("route", Q_ROUTE), ("food", Q_FOOD)]:
                key = f"{city}-{kind}"
                if key in result and len(result[key].get("answer", "")) > 100:
                    print(f"[skip] {key}")
                    continue
                question = qtpl.format(city=city)
                # 每问独立新会话
                page.goto("https://www.xiaohongshu.com/ai_chat?from=sidebar",
                          timeout=60000, wait_until="domcontentloaded")
                page.wait_for_timeout(random.randint(4000, 7000))
                try:
                    answer = ask_and_extract(page, question)
                except Exception as e:
                    print(f"[err] {key}: {str(e)[:80]}")
                    time.sleep(30)
                    continue
                if len(answer) < 300:
                    # 一次重试：回新会话再问一遍
                    print(f"[retry] {key} 回答过短({len(answer)}字)")
                    time.sleep(random.uniform(15, 25))
                    page.goto("https://www.xiaohongshu.com/ai_chat?from=sidebar",
                              timeout=60000, wait_until="domcontentloaded")
                    page.wait_for_timeout(random.randint(4000, 7000))
                    try:
                        answer2 = ask_and_extract(page, question)
                        if len(answer2) > len(answer):
                            answer = answer2
                    except Exception as e:
                        print(f"[err2] {key}: {str(e)[:80]}")
                result[key] = {"question": question, "answer": answer,
                               "chars": len(answer), "ts": time.strftime("%F %T")}
                save_result(result)
                print(f"[ok] {key}: {len(answer)} 字")
                time.sleep(random.uniform(5.0, 9.0))

        ctx.close()

    print(f"\n===== 完成：{len(result)} 条 → {OUT_FILE.name} =====")


if __name__ == "__main__":
    main()
