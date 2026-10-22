from __future__ import annotations

import json
import logging
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator
from urllib.parse import urlsplit, urlunsplit

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

from app.config import ConfigError, parse_auth_json
from app.models import Settings
from app.selectors import (
    DOUYIN_CHAT_URL,
    LOGIN_MARKERS,
    RISK_MARKERS,
    SEARCH_INPUTS,
)


LOGGER = logging.getLogger("douyin_sender")


class AuthenticationError(RuntimeError):
    pass


class RiskControlError(RuntimeError):
    pass


class SearchBoxNotReadyError(RuntimeError):
    """私信页已打开但搜索框未就绪；说明渲染慢，而非登录失效。"""


# 私信页是 SPA，domcontentloaded 之后搜索框由 JS 异步挂载，冷启动时可能超过
# 单轮等待窗口。这里做有限次数重试，并在需要时 reload，避免把慢渲染误判为认证失效。
SEARCH_BOX_RETRIES = 3
_SEARCH_RETRY_DELAY_MS = 1_500


# Collects only safe, whitelisted attributes. It deliberately reads no
# innerText / innerHTML / outerHTML / value, so page content, chat messages
# and friend nicknames can never enter the public diagnostic output.
_DOM_SNAPSHOT_JS = """() => {
  const attrs = el => ({
    tag: el.tagName.toLowerCase(),
    type: el.getAttribute('type'),
    placeholder: el.getAttribute('placeholder'),
    role: el.getAttribute('role'),
    aria_label: el.getAttribute('aria-label'),
  });
  return {
    inputs: Array.from(document.querySelectorAll('input')).map(attrs),
    textareas: Array.from(document.querySelectorAll('textarea')).map(attrs),
    contenteditable_count: document.querySelectorAll('[contenteditable="true"]').length,
    role_textbox_count: document.querySelectorAll('[role="textbox"]').length,
  };
}"""

_SAFE_ELEMENT_KEYS = ("tag", "type", "placeholder", "role", "aria_label")


@dataclass
class BrowserSession:
    page: Page
    context: BrowserContext


@asynccontextmanager
async def open_douyin(settings: Settings) -> AsyncIterator[BrowserSession]:
    playwright: Playwright | None = None
    browser: Browser | None = None
    context: BrowserContext | None = None
    try:
        playwright = await async_playwright().start()
        launch_args: dict[str, Any] = {"headless": settings.headless}
        if settings.browser_path:
            launch_args["executable_path"] = settings.browser_path
        # 额外启动参数（如 --headless=new）。
        # 实测：老式 headless 会被抖音直接弹滑块验证码，而 --headless=new
        # 走完整渲染管线，既能不弹窗口又不会被拦。
        if settings.browser_args:
            launch_args["args"] = list(settings.browser_args)
        # 使用完整 Chrome 而不是 headless shell：后者的 UA 与指纹特征明显，
        # 更容易被抖音判定为非真实浏览器。仅在未显式指定 executable_path 时生效。
        if not settings.browser_path:
            launch_args["channel"] = "chromium"

        context_args: dict[str, Any] = {
            "viewport": {"width": 1440, "height": 1000},
            # locale 与 timezone 必须和真实国内浏览器一致，否则抖音的风控
            # 很容易据此判定会话异常（尤其是海外机房 IP 的 runner）。
            "locale": "zh-CN",
            "timezone_id": "Asia/Shanghai",
            "extra_http_headers": {"Accept-Language": "zh-CN,zh;q=0.9"},
        }

        if settings.user_data_dir is not None:
            # 持久化上下文：把浏览器"设备"信息落盘，登录脚本与正式运行共用同一份。
            # 抖音只要认过这个设备，就不会每次都要求短信/刷脸验证。
            settings.user_data_dir.mkdir(parents=True, exist_ok=True)
            persistent_args = dict(launch_args)
            persistent_args["user_data_dir"] = str(settings.user_data_dir)
            # 持久化上下文不接受 storage_state（登录态本来就存在目录里）。
            persistent_args.update(context_args)
            try:
                context = await playwright.chromium.launch_persistent_context(**persistent_args)
            except Exception:
                if "channel" not in persistent_args:
                    raise
                LOGGER.warning("完整 Chromium 不可用，改用 Playwright 内置 Chromium 启动")
                persistent_args.pop("channel")
                context = await playwright.chromium.launch_persistent_context(**persistent_args)
        else:
            try:
                browser = await playwright.chromium.launch(**launch_args)
            except Exception:
                # channel="chromium" 需要本机存在该浏览器构建。没装的机器上会直接失败，
                # 这里降级回 Playwright 自带的 Chromium，保证换台电脑也能跑起来。
                if "channel" not in launch_args:
                    raise
                LOGGER.warning("完整 Chromium 不可用，改用 Playwright 内置 Chromium 启动")
                launch_args.pop("channel")
                browser = await playwright.chromium.launch(**launch_args)

            if settings.storage_state:
                state = parse_auth_json(settings.storage_state, "DOUYIN_STORAGE_STATE")
                if not isinstance(state, dict):
                    raise ConfigError("DOUYIN_STORAGE_STATE 必须是 JSON 对象")
                context_args["storage_state"] = state
            context = await browser.new_context(**context_args)

        # 隐藏最明显的自动化标记，降低被判定为机器人的概率。
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )

        # 持久化目录里已经带着登录态，不需要（也不应该）再注入 cookie。
        if settings.user_data_dir is None and not settings.storage_state and settings.cookie:
            cookies = parse_auth_json(settings.cookie, "DOUYIN_COOKIE")
            if not isinstance(cookies, list):
                raise ConfigError("DOUYIN_COOKIE 必须是 Cookie 数组")
            normalized = _normalize_cookies(cookies)
            # Cookies whose expiry has already passed are dropped by Chromium, and
            # a dropped session cookie looks exactly like an expired login. Log the
            # names (never the values) so a silent credential loss is visible.
            live = [c for c in normalized if c["expires"] == -1 or c["expires"] > time.time()]
            stale = [c["name"] for c in normalized if c not in live]
            LOGGER.info("Cookie 载入: 提供 %d 条，有效 %d 条", len(normalized), len(live))
            if stale:
                LOGGER.warning("以下 Cookie 已过期，将被浏览器丢弃: %s", ", ".join(sorted(stale)))
            if not any(c["name"] == "sessionid" for c in live):
                LOGGER.warning("Cookie 中缺少有效的 sessionid，抖音大概率会判定为未登录")
            await context.add_cookies(live)

        page = await context.new_page()
        if settings.trace:
            await context.tracing.start(screenshots=True, snapshots=True, sources=False)
        yield BrowserSession(page=page, context=context)
    finally:
        # 持久化上下文下 browser 是 None（launch_persistent_context 只返回 context），
        # 关闭 context 即关闭整个浏览器，不存在重复关闭的问题。
        if context:
            try:
                await context.close()
            except Exception:
                LOGGER.debug("关闭 context 失败（可能已随浏览器一起关闭）", exc_info=True)
        if browser:
            try:
                await browser.close()
            except Exception:
                LOGGER.debug("关闭 browser 失败", exc_info=True)
        if playwright:
            await playwright.stop()


async def verify_login(page: Page, timeout_ms: int = 15_000) -> None:
    if await _any_visible(page, RISK_MARKERS, timeout_ms=2_000):
        raise RiskControlError("抖音要求进行安全验证，任务已停止")
    if await _any_visible(page, _LOGIN_WALL_MARKERS, timeout_ms=2_000):
        raise AuthenticationError("抖音登录状态已失效")
    if not await _any_visible(page, LOGIN_MARKERS, timeout_ms=timeout_ms):
        raise AuthenticationError("未检测到抖音私信页面，登录状态可能失效或页面结构已变化")


# Hard evidence of a real login wall: the QR-code / SMS / password login UI.
# A bare promotional string such as "登录后查看更多" is deliberately NOT used,
# because it is present on the page even for a fully logged-in session, and
# treating it as proof of expiry is what turned a slow SPA render into a
# reported "登录状态失效".
_LOGIN_WALL_MARKERS = (
    'text=扫码登录',
    'text=验证码登录',
    'text=密码登录',
)
# Delay before the final confirmation pass. Transient login overlays on this SPA
# occasionally flash and then disappear once the session resolves.
_LOGIN_RECHECK_DELAY_MS = 2_500


async def open_private_messages(page: Page, timeout_ms: int = 15_000) -> None:
    await page.goto(DOUYIN_CHAT_URL, wait_until="domcontentloaded", timeout=45_000)
    # 1. Explicit risk-control page takes priority, independently of login state.
    if await _any_visible(page, RISK_MARKERS, timeout_ms=2_000):
        raise RiskControlError("抖音私信页面要求进行安全验证，任务已停止")

    # 2. Detect the friend search box. The chat page is a SPA whose search box is
    #    mounted asynchronously after domcontentloaded; a single detection round
    #    occasionally misses it on a cold runner. Retry a few times, reloading the
    #    page when the first round fails, before concluding anything.
    #
    #    The login wall is deliberately checked *after* the search box on every
    #    round: a visible search box is itself proof that the session is alive, so
    #    a login prompt rendered by a slow/unstable first paint must never be
    #    allowed to fail the run before the real content has had a chance to mount.
    saw_login_wall = False
    for attempt in range(1, SEARCH_BOX_RETRIES + 1):
        matched = await _first_visible_selector(page, SEARCH_INPUTS, timeout_ms)
        if matched is not None:
            if saw_login_wall:
                LOGGER.warning(
                    "登录提示曾短暂出现，但好友搜索框已就绪，判定为登录态正常（selector=%s）",
                    matched,
                )
            LOGGER.info("检测到好友搜索框: selector=%s, 第 %d 次尝试", matched, attempt)
            await page.wait_for_timeout(3_000)
            return

        # The search box is missing; a freshly shown login prompt may only have
        # appeared during the wait, so re-check before deciding to retry.
        if await _any_visible(page, RISK_MARKERS, timeout_ms=2_000):
            raise RiskControlError("抖音私信页面要求进行安全验证，任务已停止")
        if await _any_visible(page, _LOGIN_WALL_MARKERS, timeout_ms=2_000):
            # Remember the evidence but keep retrying: on this SPA the wall can be
            # a transient first-paint artifact. It is only treated as an expired
            # session once every retry has failed to find the search box.
            saw_login_wall = True
        if attempt < SEARCH_BOX_RETRIES:
            LOGGER.warning("未检测到好友搜索框，第 %d/%d 次尝试，准备重试", attempt, SEARCH_BOX_RETRIES)
            if attempt == 1:
                # Reload once: a fresh load usually mounts the SPA search box.
                try:
                    await page.reload(wait_until="domcontentloaded", timeout=45_000)
                except Exception:
                    LOGGER.exception("reload 失败，改为重新访问私信页面")
                    await page.goto(DOUYIN_CHAT_URL, wait_until="domcontentloaded", timeout=45_000)
            else:
                await page.wait_for_timeout(_SEARCH_RETRY_DELAY_MS)

    # 3. Search box is still missing after all attempts. Give the page one last
    #    chance to settle before deciding, so a late-mounting SPA is not reported
    #    as an expired session.
    await page.wait_for_timeout(_LOGIN_RECHECK_DELAY_MS)
    matched = await _first_visible_selector(page, SEARCH_INPUTS, timeout_ms)
    if matched is not None:
        LOGGER.info("延迟复查后检测到好友搜索框: selector=%s", matched)
        await page.wait_for_timeout(3_000)
        return

    # 4. Still nothing: emit a safe structural diagnostic and choose the exception
    #    type based on evidence. Only an explicit login-wall marker justifies
    #    AuthenticationError; a page already on /chat that merely failed to render
    #    the search box in time is reported as a transient, retryable condition.
    diagnostic = await _collect_safe_diagnostic(page, _LOGIN_WALL_MARKERS, RISK_MARKERS)
    LOGGER.error("多次重试后仍未检测到好友搜索框，页面安全诊断:\n%s", diagnostic)
    if saw_login_wall or await _any_visible(page, _LOGIN_WALL_MARKERS, timeout_ms=2_000):
        raise AuthenticationError(
            "进入抖音私信页面后登录状态失效：抖音要求重新登录（请更新 DOUYIN_COOKIE_B64 后重试）"
        )
    raise SearchBoxNotReadyError(f"私信页面已打开，但搜索框在 {SEARCH_BOX_RETRIES} 次重试后仍未就绪")


async def save_trace(session: BrowserSession, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    await session.context.tracing.stop(path=path)


async def _any_visible(page: Page, selectors: tuple[str, ...], timeout_ms: int) -> bool:
    per_selector = max(250, timeout_ms // max(1, len(selectors)))
    for selector in selectors:
        try:
            await page.locator(selector).first.wait_for(state="visible", timeout=per_selector)
            return True
        except Exception:
            continue
    return False


async def _first_visible_selector(
    page: Page,
    selectors: tuple[str, ...],
    timeout_ms: int,
) -> str | None:
    """Return the first selector whose element becomes visible, or None.

    Unlike ``_any_visible`` this also reports *which* selector matched, so the
    diagnostic can distinguish a slow render from a structural change.
    """
    per_selector = max(250, timeout_ms // max(1, len(selectors)))
    for selector in selectors:
        try:
            await page.locator(selector).first.wait_for(state="visible", timeout=per_selector)
            return selector
        except Exception:
            continue
    return None


async def _collect_safe_diagnostic(
    page: Page,
    login_markers: tuple[str, ...],
    risk_markers: tuple[str, ...],
) -> str:
    url = _safe_url(page.url)
    try:
        title = (await page.title()).strip()
    except Exception:
        title = ""

    try:
        snapshot = await page.evaluate(_DOM_SNAPSHOT_JS) or {}
    except Exception:
        snapshot = {}

    inputs = [_safe_element(item) for item in snapshot.get("inputs", [])]
    textareas = [_safe_element(item) for item in snapshot.get("textareas", [])]
    login_marker = await _any_visible(page, login_markers, timeout_ms=1_000)
    risk_marker = await _any_visible(page, risk_markers, timeout_ms=1_000)
    private_marker = await _any_visible(page, LOGIN_MARKERS, timeout_ms=1_000)

    parts = [
        f"url={url}",
        f"title={title}",
        f"inputs={json.dumps(inputs, ensure_ascii=False)}",
        f"textareas={json.dumps(textareas, ensure_ascii=False)}",
        f"role_textbox_count={snapshot.get('role_textbox_count', 0)}",
        f"contenteditable_count={snapshot.get('contenteditable_count', 0)}",
        f"login_marker={str(login_marker).lower()}",
        f"risk_marker={str(risk_marker).lower()}",
        f"private_marker={str(private_marker).lower()}",
    ]
    return "\n".join(parts)


def _safe_element(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    return {key: raw.get(key) for key in _SAFE_ELEMENT_KEYS}


def _safe_url(url: str) -> str:
    try:
        parsed = urlsplit(url)
    except ValueError:
        return ""
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def _normalize_cookies(cookies: list[Any]) -> list[dict[str, Any]]:
    normalized = []
    for index, cookie in enumerate(cookies):
        if not isinstance(cookie, dict):
            raise ConfigError(f"DOUYIN_COOKIE[{index}] 必须是对象")

        name = cookie.get("name")
        value = cookie.get("value")
        domain = cookie.get("domain")
        if name == "":
            continue
        if not isinstance(name, str) or not isinstance(value, str):
            raise ConfigError(f"DOUYIN_COOKIE[{index}] 缺少有效的 name 或 value")
        if not isinstance(domain, str) or not domain:
            raise ConfigError(f"DOUYIN_COOKIE[{index}] 缺少有效的 domain")

        expires = cookie.get("expires", cookie.get("expirationDate", -1))
        if cookie.get("session") is True:
            expires = -1
        if isinstance(expires, bool) or not isinstance(expires, (int, float)):
            expires = -1

        normalized.append(
            {
                "name": name,
                "value": value,
                "domain": domain,
                "path": cookie.get("path") if isinstance(cookie.get("path"), str) else "/",
                "expires": expires,
                "httpOnly": bool(cookie.get("httpOnly", False)),
                "secure": bool(cookie.get("secure", False)),
                "sameSite": _coerce_same_site(
                    _normalize_same_site(cookie.get("sameSite")),
                    bool(cookie.get("secure", False)),
                ),
            }
        )
    if not normalized:
        raise ConfigError("DOUYIN_COOKIE 没有有效 Cookie")
    return normalized


def _normalize_same_site(value: Any) -> str:
    mapping = {
        "strict": "Strict",
        "lax": "Lax",
        "none": "None",
        "no_restriction": "None",
    }
    return mapping.get(str(value).lower(), "Lax")


def _coerce_same_site(same_site: str, secure: bool) -> str:
    """Downgrade ``SameSite=None`` on a non-secure cookie to ``Lax``.

    Chromium rejects a cookie that declares ``SameSite=None`` without ``Secure``
    outright, so such a cookie would be silently dropped and the session would
    look expired even though the export itself was fine.
    """
    if same_site == "None" and not secure:
        return "Lax"
    return same_site
