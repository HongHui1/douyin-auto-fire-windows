import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.browser import (
    AuthenticationError,
    RiskControlError,
    SearchBoxNotReadyError,
    _collect_safe_diagnostic,
    _normalize_cookies,
    _safe_url,
    open_private_messages,
)
from app.config import ConfigError
from app.selectors import DOUYIN_CHAT_URL, LOGIN_REQUIRED_MARKERS, RISK_MARKERS


@pytest.mark.asyncio
async def test_opens_chat_directly_before_checking_login() -> None:
    page = MagicMock()
    page.goto = AsyncMock()
    page.wait_for_timeout = AsyncMock()

    with patch("app.browser._any_visible", new=AsyncMock(return_value=False)):
        with patch("app.browser._first_visible_selector", new=AsyncMock(return_value='input[placeholder*="搜索"]')):
            await open_private_messages(page)

    page.goto.assert_awaited_once_with(DOUYIN_CHAT_URL, wait_until="domcontentloaded", timeout=45_000)


def test_safe_url_strips_query_and_fragment() -> None:
    assert _safe_url("https://www.douyin.com/chat?token=SECRET&x=1#frag") == "https://www.douyin.com/chat"
    assert _safe_url("https://www.douyin.com/chat") == "https://www.douyin.com/chat"
    assert _safe_url("") == ""


@pytest.mark.asyncio
async def test_safe_diagnostic_excludes_content_and_nicknames() -> None:
    page = MagicMock()
    page.url = "https://www.douyin.com/chat?token=COOKIE_SECRET"
    page.title = AsyncMock(return_value="抖音私信")
    page.evaluate = AsyncMock(
        return_value={
            "inputs": [
                {
                    "tag": "input",
                    "type": "text",
                    "placeholder": "搜索联系人",
                    "role": None,
                    "aria_label": None,
                    "value": "张三 聊天内容",
                }
            ],
            "textareas": [{"tag": "textarea", "placeholder": "搜索", "role": None, "aria_label": None, "value": "body-inner-text"}],
            "contenteditable_count": 2,
            "role_textbox_count": 3,
        }
    )

    with patch("app.browser._any_visible", new=AsyncMock(return_value=False)):
        diagnostic = await _collect_safe_diagnostic(page, LOGIN_REQUIRED_MARKERS, RISK_MARKERS)

    # Safe attributes must show up.
    assert "url=https://www.douyin.com/chat" in diagnostic
    assert "title=抖音私信" in diagnostic
    assert '"placeholder": "搜索联系人"' in diagnostic
    assert "role_textbox_count=3" in diagnostic
    assert "contenteditable_count=2" in diagnostic
    assert "login_marker=false" in diagnostic
    assert "risk_marker=false" in diagnostic
    assert "private_marker=false" in diagnostic

    # Forbidden content must never leak.
    assert "COOKIE_SECRET" not in diagnostic
    assert "张三" not in diagnostic
    assert "聊天内容" not in diagnostic
    assert "body-inner-text" not in diagnostic
    assert "token=" not in diagnostic


@pytest.mark.asyncio
async def test_open_private_messages_logs_diagnostic_when_search_missing(caplog) -> None:
    page = MagicMock()
    page.goto = AsyncMock()
    page.reload = AsyncMock()
    page.wait_for_timeout = AsyncMock()
    page.url = "https://www.douyin.com/chat"
    page.title = AsyncMock(return_value="抖音私信")
    page.evaluate = AsyncMock(
        return_value={
            "inputs": [],
            "textareas": [],
            "contenteditable_count": 0,
            "role_textbox_count": 0,
        }
    )

    with patch("app.browser._any_visible", new=AsyncMock(return_value=False)):
        with patch("app.browser._first_visible_selector", new=AsyncMock(return_value=None)):
            with caplog.at_level(logging.ERROR, logger="douyin_sender"):
                with pytest.raises(SearchBoxNotReadyError, match="重试后仍未就绪"):
                    await open_private_messages(page)

    assert "多次重试后仍未检测到好友搜索框，页面安全诊断" in caplog.text
    assert "role_textbox_count=0" in caplog.text


@pytest.mark.asyncio
async def test_search_hit_emits_no_diagnostic(caplog) -> None:
    page = MagicMock()
    page.goto = AsyncMock()
    page.wait_for_timeout = AsyncMock()

    with patch("app.browser._any_visible", new=AsyncMock(return_value=False)):
        with patch("app.browser._first_visible_selector", new=AsyncMock(return_value='input[placeholder*="搜索"]')):
            with caplog.at_level(logging.ERROR, logger="douyin_sender"):
                await open_private_messages(page)

    assert "页面安全诊断" not in caplog.text
    page.wait_for_timeout.assert_awaited_with(3_000)


@pytest.mark.asyncio
async def test_search_box_missing_recovers_on_retry() -> None:
    page = MagicMock()
    page.goto = AsyncMock()
    page.reload = AsyncMock()
    page.wait_for_timeout = AsyncMock()

    # 首轮未就绪，reload 后第二轮命中；login/risk 标记始终不出现。
    with patch("app.browser._any_visible", new=AsyncMock(return_value=False)):
        with patch(
            "app.browser._first_visible_selector",
            new=AsyncMock(side_effect=[None, 'input[placeholder="搜索"]']),
        ):
            await open_private_messages(page)

    page.reload.assert_awaited_once_with(wait_until="domcontentloaded", timeout=45_000)


@pytest.mark.asyncio
async def test_search_box_falls_back_to_goto_when_reload_fails() -> None:
    page = MagicMock()
    page.goto = AsyncMock()
    page.reload = AsyncMock(side_effect=RuntimeError("reload 失败"))
    page.wait_for_timeout = AsyncMock()

    with patch("app.browser._any_visible", new=AsyncMock(return_value=False)):
        with patch(
            "app.browser._first_visible_selector",
            new=AsyncMock(side_effect=[None, 'input[placeholder*="搜索"]']),
        ):
            await open_private_messages(page)

    page.reload.assert_awaited_once()
    assert page.goto.await_count >= 2  # 初次访问 + reload 失败后的重新访问


@pytest.mark.asyncio
async def test_risk_control_still_raises_before_search_check() -> None:
    page = MagicMock()
    page.goto = AsyncMock()

    with patch("app.browser._any_visible", new=AsyncMock(return_value=True)):
        with pytest.raises(RiskControlError, match="安全验证"):
            await open_private_messages(page)


@pytest.mark.asyncio
async def test_login_wall_raises_after_all_retries() -> None:
    """登录墙只在重试全部失败后才判定为登录失效。

    这是本次修复的核心行为：过去一检测到登录提示就立刻抛 AuthenticationError，
    把「首屏渲染慢 / 登录浮层闪现」误报成了「登录状态失效」。
    """
    page = _login_wall_page()

    with pytest.raises(AuthenticationError, match="登录状态失效"):
        await open_private_messages(page)

    # 三轮重试都要跑完，才允许下结论
    assert page.reload.await_count == 1
    assert page.wait_for_timeout.await_count >= 2


def _login_wall_page() -> MagicMock:
    """构造一个「真实登录墙」页面：只有登录墙选择器可见，搜索框始终找不到。

    通过让 locator.wait_for 依据选择器内容决定成功或超时，
    使真实的 _any_visible / _first_visible_selector 逻辑得以执行，
    而不是把结论硬编码进 mock。
    """
    page = MagicMock()
    page.goto = AsyncMock()
    page.reload = AsyncMock()
    page.wait_for_timeout = AsyncMock()
    page.url = "https://www.douyin.com/chat"
    page.title = AsyncMock(return_value="抖音")
    page.evaluate = AsyncMock(
        return_value={
            "inputs": [],
            "textareas": [],
            "contenteditable_count": 0,
            "role_textbox_count": 0,
        }
    )

    def make_locator(selector: str):
        locator = MagicMock()
        is_login_wall = "扫码登录" in selector or "验证码登录" in selector or "密码登录" in selector

        async def wait_for(state=None, timeout=None):
            if is_login_wall:
                return
            raise TimeoutError(f"not visible: {selector}")

        locator.first.wait_for = AsyncMock(side_effect=wait_for)
        return locator

    page.locator = MagicMock(side_effect=make_locator)
    return page

    # 三轮重试都要跑完，才允许下结论
    assert page.reload.await_count == 1
    assert page.wait_for_timeout.await_count >= 2


@pytest.mark.asyncio
async def test_transient_login_flash_does_not_fail_when_search_box_appears() -> None:
    """搜索框最终出现时，中途闪现过的登录提示不应导致失败。"""
    page = MagicMock()
    page.goto = AsyncMock()
    page.reload = AsyncMock()
    page.wait_for_timeout = AsyncMock()

    # 第 1 轮搜索框未就绪、登录提示出现；第 2 轮搜索框就绪。
    with patch("app.browser._any_visible", new=AsyncMock(return_value=False)):
        with patch(
            "app.browser._first_visible_selector",
            new=AsyncMock(side_effect=[None, 'input[placeholder*="搜索"]']),
        ):
            await open_private_messages(page)

    page.reload.assert_awaited_once()


def test_normalizes_cookie_editor_export() -> None:
    cookies = [
        {
            "domain": ".douyin.com",
            "expirationDate": 1800175766.5,
            "hostOnly": False,
            "httpOnly": True,
            "name": "UIFID",
            "path": "/",
            "sameSite": "no_restriction",
            "secure": True,
            "session": False,
            "storeId": None,
            "value": "token",
        }
    ]

    assert _normalize_cookies(cookies) == [
        {
            "name": "UIFID",
            "value": "token",
            "domain": ".douyin.com",
            "path": "/",
            "expires": 1800175766.5,
            "httpOnly": True,
            "secure": True,
            "sameSite": "None",
        }
    ]


def test_session_cookie_ignores_expiration_date() -> None:
    cookies = [
        {
            "domain": ".douyin.com",
            "expirationDate": 1800175766.5,
            "name": "sessionid",
            "session": True,
            "value": "token",
        }
    ]

    assert _normalize_cookies(cookies)[0]["expires"] == -1


def test_ignores_cookie_editor_empty_name_artifact() -> None:
    cookies = [
        {"domain": "www.douyin.com", "name": "", "value": "douyin.com"},
        {"domain": ".douyin.com", "name": "sessionid", "value": "token"},
    ]

    assert [cookie["name"] for cookie in _normalize_cookies(cookies)] == ["sessionid"]


def test_rejects_cookie_without_domain() -> None:
    with pytest.raises(ConfigError, match="缺少有效的 domain"):
        _normalize_cookies([{"name": "UIFID", "value": "token"}])
