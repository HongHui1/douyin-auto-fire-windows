from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from playwright.async_api import async_playwright
from dotenv import load_dotenv

from app.browser import _LOGIN_WALL_MARKERS


DOUYIN_URL = "https://www.douyin.com/"
CHAT_URL = "https://www.douyin.com/chat"

# 与正式运行共用同一个浏览器配置目录 —— 这是关键。
# 抖音会把「设备」信息记在这个目录里：这里验证过一次之后，
# 后续自动运行沿用同一目录，就不会再被要求短信/刷脸验证。
load_dotenv(PROJECT_ROOT / ".env")
_profile = Path(os.getenv("DOUYIN_USER_DATA_DIR", ".browser-profile")).expanduser()
USER_DATA_DIR = _profile if _profile.is_absolute() else PROJECT_ROOT / _profile

# 完成扫码 + 可能的短信/刷脸验证需要多久就等多久。
LOGIN_TIMEOUT_SECONDS = 600
POLL_INTERVAL_SECONDS = 5

_RISK_MARKERS = ("text=安全验证", "text=完成验证", "text=验证身份", "text=请完成下列验证")
_SEARCH_BOXES = (
    'input[placeholder*="搜索"]',
    '[role="textbox"][placeholder*="搜索"]',
    'input[aria-label*="搜索"]',
)


async def login(console: bool = True) -> None:
    async with async_playwright() as playwright:
        USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
        context = await _launch(playwright)
        page = context.pages[0] if context.pages else await context.new_page()

        if console:
            _print_instructions()

        try:
            await page.goto(CHAT_URL, wait_until="domcontentloaded", timeout=45_000)
            await page.wait_for_timeout(4_000)
        except Exception as exc:  # noqa: BLE001
            print(f"首次打开页面失败（不影响，继续等待）: {str(exc)[:100]}")

        try:
            ok = await _wait_until_logged_in(page, console)
            if ok:
                print()
                print("登录成功 ✓  设备与登录状态已保存到:")
                print(f"  {USER_DATA_DIR}")
                return
            print("登录等待超时，将关闭本次浏览器。请重新运行登录脚本继续验证。")
            print("已保存的设备数据保留在同一目录；是否需要再次验证由抖音决定。")
            raise SystemExit(1)
        finally:
            await context.close()


def _print_instructions() -> None:
    print()
    print("=" * 66)
    print("请在弹出的浏览器窗口里完成登录：")
    print("  1. 用手机抖音 App 扫描页面上的二维码")
    print("  2. 如果抖音要求短信验证 / 刷脸验证，按提示完成")
    print("     —— 这是正常的一次性设备验证，完成后会被记住")
    print("  3. 直到页面右上角显示你的头像")
    print()
    print("⚠️ 脚本会一直等到「能正常打开私信页」才判定成功。")
    print("⚠️ 在那之前请不要关闭浏览器窗口。")
    print(f"   最长等待 {LOGIN_TIMEOUT_SECONDS // 60} 分钟。")
    print("=" * 66)
    print()


async def _launch(playwright):
    args = {
        "user_data_dir": str(USER_DATA_DIR),
        "headless": False,  # 登录必须可见：无头模式会被抖音直接弹验证码
        "viewport": {"width": 1440, "height": 1000},
        "locale": "zh-CN",
        "timezone_id": "Asia/Shanghai",
        "extra_http_headers": {"Accept-Language": "zh-CN,zh;q=0.9"},
    }
    try:
        return await playwright.chromium.launch_persistent_context(channel="chromium", **args)
    except Exception:
        return await playwright.chromium.launch_persistent_context(**args)


async def _wait_until_logged_in(page, console: bool) -> bool:
    """唯一的成功判据：私信页的好友搜索框可见。

    曾经用「首页出现 私信/朋友/我的 入口」来判断登录，但未登录的首页同样有这些入口，
    于是脚本在你完成验证之前就误判成功、把浏览器关掉了 —— 这正是登录态没保存的原因。
    现在只认真正的硬证据，并保留浏览器窗口直到确认或超时。
    """
    deadline = time.time() + LOGIN_TIMEOUT_SECONDS
    started = time.time()
    attempt = 0
    last_beat = 0.0

    while time.time() < deadline:
        attempt += 1

        # 如果用户已经在别处登录成功，这一步会自己变成已登录状态
        try:
            if not page.url.startswith(CHAT_URL):
                await page.goto(CHAT_URL, wait_until="domcontentloaded", timeout=45_000)
                await page.wait_for_timeout(3_000)
            else:
                await page.wait_for_timeout(POLL_INTERVAL_SECONDS * 1_000)
        except Exception:
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
            continue

        if await _any_visible(page, _SEARCH_BOXES, 3_000):
            return True

        if console:
            if await _any_visible(page, _RISK_MARKERS, 1_000):
                status = "检测到安全验证，请在浏览器里完成验证……"
            elif await _any_visible(page, _LOGIN_WALL_MARKERS, 1_000):
                status = "尚未登录（页面显示登录/验证界面），请继续在浏览器里操作……"
            else:
                status = "私信页还没就绪，继续等待……"

            if attempt == 1 or attempt % 6 == 0:
                waited = int(time.time() - started)
                left = int(deadline - time.time())
                print(f"  [{waited:>3}s] {status}  (剩余约 {left // 60} 分 {left % 60} 秒)")
                last_beat = time.time()

        await asyncio.sleep(POLL_INTERVAL_SECONDS)

    _ = last_beat
    return False


async def _any_visible(page, selectors, timeout_ms: int) -> bool:
    per = max(300, timeout_ms // max(1, len(selectors)))
    for selector in selectors:
        try:
            await page.locator(selector).first.wait_for(state="visible", timeout=per)
            return True
        except Exception:
            continue
    return False


if __name__ == "__main__":
    asyncio.run(login())
