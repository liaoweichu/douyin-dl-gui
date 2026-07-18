"""AuthBot 单元测试。

Playwright 在测试环境中通过 mock 模拟，无需真实浏览器。
若 playwright 未安装，整个模块跳过。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

# auth_bot 模块顶部 `from playwright.sync_api import ...`，
# 因此需要 playwright 已安装才能 import。否则跳过整个文件。
pytest.importorskip("playwright")

from douyin_dl.auth_bot import AuthBot, AuthError


def test_auth_error_is_exception() -> None:
    """AuthError 应是 Exception 的子类。"""
    assert isinstance(AuthError("x"), Exception)


def test_login_url_constant() -> None:
    assert AuthBot.LOGIN_URL == "https://www.douyin.com/"


def test_login_cookie_name_constant() -> None:
    assert AuthBot.LOGIN_COOKIE_NAME == "passport_csrf_token"


def test_default_timeout_constant() -> None:
    assert AuthBot.DEFAULT_TIMEOUT == 300.0


def _build_playwright_mocks():
    """构造 sync_playwright 链路的 mock 对象，返回 (cm, browser, context)。"""
    mock_pw_cm = MagicMock()
    mock_pw_cm.__exit__.return_value = False
    mock_pw = mock_pw_cm.__enter__.return_value
    mock_browser = mock_pw.chromium.launch.return_value
    mock_context = mock_browser.new_context.return_value
    _mock_page = mock_context.new_page.return_value
    return mock_pw_cm, mock_browser, mock_context


def test_login_returns_cookies_when_cookie_appears() -> None:
    """第二次轮询时出现登录 Cookie，login 返回全部 cookies。"""
    with patch("douyin_dl.auth_bot.sync_playwright") as mock_sync_pw, \
         patch("douyin_dl.auth_bot.time.sleep") as mock_sleep:
        mock_pw_cm, mock_browser, mock_context = _build_playwright_mocks()
        mock_sync_pw.return_value = mock_pw_cm

        target_cookie = {"name": "passport_csrf_token", "value": "abc"}
        mock_context.cookies.side_effect = [
            [],
            [target_cookie],
        ]

        auth_bot = AuthBot()
        result = auth_bot.login()

        assert result == [target_cookie]
        # 第一次和第二次 cookies() 之间应 sleep 过一次
        assert mock_sleep.called
        # 返回前应关闭浏览器（finally 触发）
        mock_browser.close.assert_called()


def test_login_timeout_raises_auth_error() -> None:
    """cookie 始终不出现，超过 timeout 后抛 AuthError。"""
    with patch("douyin_dl.auth_bot.sync_playwright") as mock_sync_pw, \
         patch("douyin_dl.auth_bot.time.sleep"):
        mock_pw_cm, mock_browser, mock_context = _build_playwright_mocks()
        mock_sync_pw.return_value = mock_pw_cm
        mock_context.cookies.return_value = []

        auth_bot = AuthBot(timeout=0.5)
        with pytest.raises(AuthError):
            auth_bot.login()

        # 即使超时，也应关闭浏览器
        mock_browser.close.assert_called()
