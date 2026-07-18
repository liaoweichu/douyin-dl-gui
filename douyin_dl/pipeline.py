"""批量下载管线：串行调度 URL 列表，按 parse → fetch → (browser fallback) → download 流转。"""

from __future__ import annotations

import datetime
import random
import sys
import threading
import time
from typing import Callable, Optional

import httpx

from douyin_dl.auth_bot import AuthBot
from douyin_dl.browser_fallback import BrowserFallback, BrowserFallbackError
from douyin_dl.cookie_store import CookieStore
from douyin_dl.downloader import DownloadError, Downloader
from douyin_dl.fetcher import FetcherError, fetch
from douyin_dl.file_namer import FileNamer
from douyin_dl.link_parser import LinkParserError, parse_input
from douyin_dl.models import Config, VideoMeta
from douyin_dl.progress import (
    EVENT_AUTH_REQUIRED,
    EVENT_BATCH_FINISHED,
    EVENT_BATCH_STARTED,
    EVENT_DOWNLOAD_PROGRESS,
    EVENT_ITEM_FINISHED,
    EVENT_ITEM_STARTED,
    EVENT_LOG,
    EVENT_STAGE,
    PipelineStats,
    ProgressEvent,
)


class DownloadPipeline:
    """串行调度批量下载。"""

    def __init__(
        self,
        config: Config,
        cookie_store: Optional[CookieStore] = None,
        auth_bot: Optional[AuthBot] = None,
        browser_fallback: Optional[BrowserFallback] = None,
        downloader: Optional[Downloader] = None,
        # Injectable for testing. None means "real fetch". Pass a callable taking
        # (aweme_id, client) -> VideoMeta.
        fetch_fn: Optional[Callable[[str, httpx.Client], VideoMeta]] = None,
        # Injectable for testing. None means "real BrowserFallback". Pass a callable
        # taking (aweme_id, cookies, kind) -> str.
        browser_fallback_fn: Optional[Callable[[str, list, str], str]] = None,
        progress_callback: Optional[Callable[[ProgressEvent], None]] = None,
        cancel_event: Optional[threading.Event] = None,
        download_progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ) -> None:
        self._config = config
        self._cookie_store = cookie_store or CookieStore(config.cookie_path)
        self._auth_bot = auth_bot or AuthBot()
        self._browser_fallback = browser_fallback or BrowserFallback()
        self._downloader = downloader or Downloader()
        self._injected_downloader = downloader is not None
        self._fetch_fn = fetch_fn or fetch
        self._browser_fallback_fn = browser_fallback_fn
        self._progress_cb = progress_callback
        self._cancel_event = cancel_event
        self._download_progress_cb = download_progress_callback

    def _emit(self, event: ProgressEvent) -> None:
        """投递事件到 callback；若未设置 callback 则忽略。"""
        if self._progress_cb is not None:
            self._progress_cb(event)

    def _print(self, msg: str, file=None) -> None:
        """只在未设置 progress_callback 时打印（保持 CLI 行为）。"""
        if self._progress_cb is None:
            print(msg, file=file or sys.stdout)

    def _reauth(self) -> list[dict]:
        self._print("Cookie 失效，启动登录...", file=sys.stderr)
        cookies = self._auth_bot.login()
        self._cookie_store.save(cookies, time.time())
        return cookies

    def _inject_cookies(self, client: httpx.Client, cookies: list[dict]) -> None:
        """将 Playwright 格式的 cookie 列表注入到 httpx client。"""
        client.cookies.clear()
        for c in cookies:
            client.cookies.set(
                c["name"], c["value"], domain=c.get("domain", "")
            )

    def run(self, urls: list[str]) -> PipelineStats:
        """Process all URLs serially. Returns PipelineStats.
        Always returns; never raises (errors are caught per-item).
        """
        stats = PipelineStats()
        self._config.output_dir.mkdir(parents=True, exist_ok=True)

        # Cookie management at start.
        cookies: list[dict] = self._cookie_store.get_cookies()
        if self._config.reauth or not cookies or self._cookie_store.is_expired():
            cookies = self._reauth()

        client = httpx.Client(timeout=30, follow_redirects=True)
        self._inject_cookies(client, cookies)

        downloader = (
            self._downloader
            if self._injected_downloader
            else Downloader(client=client)
        )

        n = len(urls)
        self._emit(ProgressEvent(type=EVENT_BATCH_STARTED, total=n))
        try:
            for idx, url in enumerate(urls):
                if self._cancel_event is not None and self._cancel_event.is_set():
                    # 剩余项标记为 skipped 并退出循环。
                    stats.skipped += n - idx
                    break
                self._emit(
                    ProgressEvent(
                        type=EVENT_ITEM_STARTED, url=url, index=idx, total=n
                    )
                )
                try:
                    cookies = self._process_one(
                        url, client, downloader, cookies, stats,
                        idx=idx, total=n,
                    )
                except Exception as e:  # pragma: no cover - defensive
                    self._record_failure(
                        url, f"未处理异常: {e}", stats, idx=idx, total=n
                    )
                if idx < n - 1:
                    time.sleep(random.uniform(*self._config.sleep_range))
        finally:
            client.close()

        self._print(
            f"完成：成功 {stats.success} 条，失败 {stats.failed} 条，"
            f"跳过 {stats.skipped} 条"
        )
        self._emit(ProgressEvent(type=EVENT_BATCH_FINISHED, stats=stats))
        return stats

    def _process_one(
        self,
        url: str,
        client: httpx.Client,
        downloader: Downloader,
        cookies: list[dict],
        stats: PipelineStats,
        idx: int = 0,
        total: int = 0,
    ) -> list[dict]:
        """处理单个 URL。返回（可能更新后的）cookies 列表。"""
        # 1. 解析输入。
        self._emit(
            ProgressEvent(
                type=EVENT_STAGE, url=url, index=idx, total=total, stage="parse"
            )
        )
        try:
            aweme_id, _short = parse_input(url, client=client)
        except LinkParserError as e:
            self._record_failure(
                url, f"链接解析失败: {e}", stats, idx=idx, total=total
            )
            return cookies

        # 2. 抓取元数据；FetcherError 时回退到 BrowserFallback。
        self._emit(
            ProgressEvent(
                type=EVENT_STAGE, url=url, index=idx, total=total, stage="fetch"
            )
        )
        try:
            meta = self._fetch_fn(aweme_id, client)
        except FetcherError:
            meta = self._try_browser_fallback(
                aweme_id, cookies, stats, url, idx=idx, total=total
            )
            if meta is None:
                return cookies

        # 3. 校验 video_url。
        if not meta.video_url:
            self._record_failure(url, "no video_url", stats, idx=idx, total=total)
            return cookies

        # 4. 构建文件名。
        save_path = FileNamer.build(meta, self._config.output_dir)

        # 5. 下载。
        self._emit(
            ProgressEvent(
                type=EVENT_STAGE, url=url, index=idx, total=total, stage="download"
            )
        )
        progress_cb: Optional[Callable[[int, int], None]] = None
        if self._download_progress_cb is not None:
            progress_cb = lambda d, t: self._download_progress_cb(url, d, t)
        try:
            downloaded = downloader.download(
                meta.video_url, save_path, desc=meta.aweme_id,
                progress_callback=progress_cb,
            )
        except DownloadError as e:
            msg = str(e)
            if "401" in msg or "403" in msg:
                # 触发重新登录并重试一次。
                cookies = self._reauth()
                self._inject_cookies(client, cookies)
                try:
                    downloaded = downloader.download(
                        meta.video_url, save_path, desc=meta.aweme_id,
                        progress_callback=progress_cb,
                    )
                except DownloadError as e2:
                    self._record_failure(
                        url, f"重试下载失败: {e2}", stats, idx=idx, total=total
                    )
                    return cookies
            else:
                self._record_failure(
                    url, f"下载失败: {e}", stats, idx=idx, total=total
                )
                return cookies

        # 6. 计数。
        if downloaded:
            stats.success += 1
            self._emit(
                ProgressEvent(
                    type=EVENT_ITEM_FINISHED, url=url, index=idx, total=total,
                    status="success",
                )
            )
        else:
            stats.skipped += 1
            self._emit(
                ProgressEvent(
                    type=EVENT_ITEM_FINISHED, url=url, index=idx, total=total,
                    status="skipped",
                )
            )

        return cookies

    def _try_browser_fallback(
        self,
        aweme_id: str,
        cookies: list[dict],
        stats: PipelineStats,
        url: str,
        idx: int = 0,
        total: int = 0,
    ) -> Optional[VideoMeta]:
        """Fetcher 失败时，依次尝试 video / note 两种页面用浏览器兜底。"""
        self._emit(
            ProgressEvent(
                type=EVENT_STAGE, url=url, index=idx, total=total, stage="fallback"
            )
        )
        for kind in ("video", "note"):
            try:
                if self._browser_fallback_fn is not None:
                    fetched_url = self._browser_fallback_fn(
                        aweme_id, cookies, kind
                    )
                else:
                    fetched_url = self._browser_fallback.fetch_video_url(
                        aweme_id, cookies, kind=kind
                    )
                return VideoMeta(
                    aweme_id=aweme_id, video_url=fetched_url, type="unknown"
                )
            except BrowserFallbackError:
                continue
        self._record_failure(
            url, "分享页与浏览器兜底均失败", stats, idx=idx, total=total
        )
        return None

    def _record_failure(
        self,
        url: str,
        reason: str,
        stats: PipelineStats,
        idx: int = 0,
        total: int = 0,
    ) -> None:
        """记录失败项：累加计数、写 errors.log、打印 stderr。"""
        stats.failed += 1
        stats.failed_urls.append((url, reason))
        self._print(f"失败: {url} — {reason}", file=sys.stderr)
        ts = datetime.datetime.now().isoformat()
        try:
            log_path = self._config.output_dir / "errors.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as f:
                f.write(f"[{ts}] {url} {reason}\n")
        except OSError as e:
            self._print(f"无法写入 errors.log: {e}", file=sys.stderr)
        self._emit(
            ProgressEvent(
                type=EVENT_ITEM_FINISHED, url=url, index=idx, total=total,
                status="failed", reason=reason,
            )
        )
