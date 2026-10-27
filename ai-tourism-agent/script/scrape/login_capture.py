# -*- coding: utf-8 -*-
"""
登录态捕获脚本：弹出真实浏览器窗口，用户手动登录小红书 / 12306，
脚本自动检测登录成功并保存 storage_state（Cookie + localStorage），
供后续爬虫脚本通过 storage_state= 参数复用。

用法：
    python login_capture.py            # 依次登录两个站点
    python login_capture.py --only xhs # 只登录小红书
    python login_capture.py --only 12306
"""
import argparse
import time
from pathlib import Path

from patchright.sync_api import sync_playwright

HERE = Path(__file__).parent
PROFILE_DIR = HERE / "browser_profile"      # 持久化浏览器配置（保留登录态）
CAPTURED = HERE / "captured"
CAPTURED.mkdir(exist_ok=True)

SITES = {
    "xhs": {
        "name": "小红书",
        "start": "https://www.xiaohongshu.com/",
        "state_file": CAPTURED / "xhs_state.json",
        # 登录成功标志：调用 /api/sns/web/v2/user/me 返回真实用户（匿名访客也有 web_session Cookie，不能作为判据）
        "check": lambda ctx, page: _xhs_is_login(page),
    },
    "12306": {
        "name": "12306",
        "start": "https://kyfw.12306.cn/otn/view/index.html",
        "state_file": CAPTURED / "train12306_state.json",
        # 登录成功标志：页面出现"退出"按钮（登录后才显示）
        "check": lambda ctx, page: _has_logout(page),
    },
}


def _has_logout(page) -> bool:
    try:
        return page.evaluate("() => document.body ? document.body.innerText.includes('退出') : false")
    except Exception:
        return False


def _xhs_is_login(page) -> bool:
    """DOM 判定：登录后页面不再出现「登录」字样（/user/me 接口需签名头，不可用）"""
    try:
        return page.evaluate(
            "() => !/登录/.test(document.body.innerText) && !!document.querySelector('[class*=avatar]')"
        )
    except Exception:
        return False


def wait_login(site_key: str, ctx, page, timeout_min: int = 15) -> bool:
    site = SITES[site_key]
    print(f"\n>>> 请在弹出的浏览器窗口里登录【{site['name']}】（扫码/账密均可）")
    print(f">>> 最多等待 {timeout_min} 分钟，登录成功脚本会自动检测并保存……")
    deadline = time.time() + timeout_min * 60
    while time.time() < deadline:
        try:
            if site["check"](ctx, page):
                print(f"✔ 检测到【{site['name']}】登录态，保存到 {site['state_file'].name}")
                ctx.storage_state(path=str(site["state_file"]))
                return True
        except Exception:
            pass
        time.sleep(3)
    print(f"✘ 等待超时，未检测到【{site['name']}】登录态")
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["xhs", "12306"], help="只登录指定站点")
    ap.add_argument("--timeout", type=int, default=15, help="每个站点等待分钟数")
    args = ap.parse_args()

    targets = [args.only] if args.only else ["xhs", "12306"]

    with sync_playwright() as p:
        # 持久化配置目录：下次运行不用重新登录（直到 Cookie 过期）
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            viewport=None,  # 跟随窗口尺寸
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            args=[
                "--disable-blink-features=AutomationControlled",
                "--start-maximized",
                "--window-position=0,0",
                "--no-first-run",
            ],
        )
        results = {}
        for key in targets:
            site = SITES[key]
            page = ctx.new_page()
            page.bring_to_front()
            page.goto(site["start"], timeout=60000, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)
            # 若持久化配置里已有登录态，直接确认保存
            if site["check"](ctx, page):
                print(f"✔ 检测到已有【{site['name']}】登录态，直接保存")
                ctx.storage_state(path=str(site["state_file"]))
                results[key] = True
            else:
                results[key] = wait_login(key, ctx, page, args.timeout)
            page.close()

        print("\n===== 登录捕获结果 =====")
        for k, ok in results.items():
            state = SITES[k]["state_file"]
            print(f"{'✔' if ok else '✘'} {SITES[k]['name']}: {'已保存 ' + str(state) if ok else '未获取'}")
        print("\n浏览器保留打开状态可继续手动浏览；脚本即将退出。")
        ctx.close()


if __name__ == "__main__":
    main()
