"""Playwright 浏览器兜底：当 httpx Fetcher 失败时，用 headless Chromium 打开页面读 <video> currentSrc。"""

from __future__ import annotations

from typing import Optional

from playwright.sync_api import sync_playwright


class BrowserFallbackError(Exception):
    """Raised when browser fallback fails to extract video URL."""


class BrowserFallback:
    """Playwright-based fallback: open the page in headless Chromium, read <video> currentSrc."""

    VIDEO_URL_TEMPLATE = "https://www.douyin.com/video/{aweme_id}"
    NOTE_URL_TEMPLATE = "https://www.douyin.com/note/{aweme_id}"
    DEFAULT_TIMEOUT = 30_000  # ms, for page.wait_for_selector

    def __init__(self, timeout_ms: int = None) -> None:
        self._timeout = self.DEFAULT_TIMEOUT if timeout_ms is None else timeout_ms

    def fetch_video_url(self, aweme_id: str, cookies: list[dict], kind: str = "video") -> str:
        """Open the page (kind='video' or 'note'), inject cookies, wait for <video>,
        return its currentSrc. Raise BrowserFallbackError on any failure.
        """
        if kind == "video":
            url = self.VIDEO_URL_TEMPLATE.format(aweme_id=aweme_id)
        else:
            url = self.NOTE_URL_TEMPLATE.format(aweme_id=aweme_id)

        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(
                    headless=True,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-sandbox",
                    ],
                )
                try:
                    context = browser.new_context(
                        viewport={"width": 1280, "height": 800},
                        user_agent=(
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/120.0.0.0 Safari/537.36"
                        ),
                    )
                    # 注入 cookie 必须在 goto 之前完成。
                    context.add_cookies(cookies)

                    page = context.new_page()
                    page.goto(url, wait_until="domcontentloaded")

                    try:
                        page.wait_for_selector("video", timeout=self._timeout)
                    except Exception:
                        raise BrowserFallbackError("未找到 <video> 元素")

                    current_src = page.evaluate(
                        "() => document.querySelector('video')?.currentSrc"
                    )
                    if not current_src:
                        raise BrowserFallbackError("<video> 元素的 currentSrc 为空")

                    return current_src
                finally:
                    browser.close()
        except BrowserFallbackError:
            raise
        except Exception as e:
            raise BrowserFallbackError(f"浏览器兜底失败: {e}")
