"""BrowserFallback 单元测试，使用 unittest.mock 模拟 Playwright，无需真实浏览器。"""

from __future__ import annotations

import pytest

# 模块 browser_fallback 顶层 import 了 playwright.sync_api，
# 因此 playwright 必须可用才能导入被测模块。
pytest.importorskip("playwright")

from unittest.mock import patch  # noqa: E402

from douyin_dl.browser_fallback import BrowserFallback, BrowserFallbackError  # noqa: E402


def test_browser_fallback_error_is_exception() -> None:
    """BrowserFallbackError 应当是 Exception 的子类。"""
    assert isinstance(BrowserFallbackError("x"), Exception)


def test_constants() -> None:
    """类常量符合预期。"""
    assert BrowserFallback.VIDEO_URL_TEMPLATE == "https://www.douyin.com/video/{aweme_id}"
    assert BrowserFallback.NOTE_URL_TEMPLATE == "https://www.douyin.com/note/{aweme_id}"
    assert BrowserFallback.DEFAULT_TIMEOUT == 30_000


def test_fetch_video_url_success() -> None:
    """成功路径：mock 返回 currentSrc，方法返回该 URL，cookies 已注入，goto 指向 video URL。"""
    with patch("douyin_dl.browser_fallback.sync_playwright") as mock_pw:
        cm = mock_pw.return_value
        pw = cm.__enter__.return_value  # playwright
        browser = pw.chromium.launch.return_value
        context = browser.new_context.return_value
        page = context.new_page.return_value
        # wait_for_selector 默认返回 MagicMock（truthy），代表找到 <video>。
        page.evaluate.return_value = "https://example.com/video.mp4"

        result = BrowserFallback().fetch_video_url("123", [], kind="video")

    assert result == "https://example.com/video.mp4"
    # cookies 在 goto 之前注入。
    context.add_cookies.assert_called_once_with([])
    # goto 指向 video 模板 URL。
    page.goto.assert_called_once_with(
        "https://www.douyin.com/video/123",
        wait_until="domcontentloaded",
    )


def test_fetch_video_url_empty_currentsrc_raises() -> None:
    """currentSrc 为空字符串时应抛 BrowserFallbackError，消息包含 'currentSrc 为空'。"""
    with patch("douyin_dl.browser_fallback.sync_playwright") as mock_pw:
        cm = mock_pw.return_value
        pw = cm.__enter__.return_value
        browser = pw.chromium.launch.return_value
        context = browser.new_context.return_value
        page = context.new_page.return_value
        page.evaluate.return_value = ""

        with pytest.raises(BrowserFallbackError) as excinfo:
            BrowserFallback().fetch_video_url("123", [], kind="video")

    assert "currentSrc 为空" in str(excinfo.value)


def test_fetch_video_url_selector_timeout_raises() -> None:
    """wait_for_selector 抛异常时应转为 BrowserFallbackError，消息包含 '未找到'。"""
    with patch("douyin_dl.browser_fallback.sync_playwright") as mock_pw:
        cm = mock_pw.return_value
        pw = cm.__enter__.return_value
        browser = pw.chromium.launch.return_value
        context = browser.new_context.return_value
        page = context.new_page.return_value
        # 模拟选择器等待超时/失败。
        page.wait_for_selector.side_effect = Exception("selector timeout")

        with pytest.raises(BrowserFallbackError) as excinfo:
            BrowserFallback().fetch_video_url("123", [], kind="video")

    assert "未找到" in str(excinfo.value)


def test_fetch_note_url() -> None:
    """kind='note' 时 goto 指向 note 模板 URL。"""
    with patch("douyin_dl.browser_fallback.sync_playwright") as mock_pw:
        cm = mock_pw.return_value
        pw = cm.__enter__.return_value
        browser = pw.chromium.launch.return_value
        context = browser.new_context.return_value
        page = context.new_page.return_value
        page.evaluate.return_value = "https://example.com/video.mp4"

        result = BrowserFallback().fetch_video_url("456", [], kind="note")

    assert result == "https://example.com/video.mp4"
    page.goto.assert_called_once_with(
        "https://www.douyin.com/note/456",
        wait_until="domcontentloaded",
    )
