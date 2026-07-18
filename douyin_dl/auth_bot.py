"""基于 Playwright 的抖音登录流程。

启动可见浏览器，导航到 https://www.douyin.com/，
等待用户扫码完成登录后导出全部 Cookie。
"""

from __future__ import annotations

import time

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright


class AuthError(Exception):
    """Raised when login fails or times out."""


class AuthBot:
    """Playwright-based login flow for douyin.com."""

    LOGIN_URL = "https://www.douyin.com/"
    # Cookie name that indicates login completed (set by passport service after auth)
    LOGIN_COOKIE_NAME = "passport_csrf_token"
    DEFAULT_TIMEOUT = 300.0  # 5 minutes max wait

    def __init__(self, timeout: float = None) -> None:
        self._timeout = self.DEFAULT_TIMEOUT if timeout is None else timeout

    def login(self, headless: bool = False) -> list[dict]:
        """Launch visible browser, open LOGIN_URL, wait for user to scan QR.

        Returns list of cookie dicts (Playwright format: {name, value, domain, path, ...}).
        Raises AuthError on timeout or browser error.
        """
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=headless,
                    args=["--disable-blink-features=AutomationControlled"],
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
                    page = context.new_page()
                    page.goto(self.LOGIN_URL)
                    print(
                        "请使用抖音 App 扫描页面二维码完成登录"
                        "（最长等待 5 分钟）..."
                    )

                    start = time.time()
                    while True:
                        cookies = context.cookies()
                        for cookie in cookies:
                            if (
                                cookie.get("name") == self.LOGIN_COOKIE_NAME
                                and cookie.get("value")
                            ):
                                print(f"登录成功，已获取 {len(cookies)} 个 Cookie")
                                return cookies
                        if (time.time() - start) >= self._timeout:
                            raise AuthError(
                                "登录超时（5 分钟内未检测到登录 Cookie）"
                            )
                        time.sleep(2)
                finally:
                    browser.close()
        except AuthError:
            raise
        except PlaywrightError as e:
            raise AuthError(f"登录过程中发生 Playwright 错误: {e}") from e
        except Exception as e:  # pragma: no cover - 防御性兜底
            raise AuthError(f"登录过程中发生未知错误: {e}") from e
