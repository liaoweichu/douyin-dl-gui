"""httpx 流式下载器，支持 Range 续传与防盗链 Referer。"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

import httpx
from tqdm import tqdm


BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class DownloadError(Exception):
    """Raised when download fails."""


class Downloader:
    """httpx 流式下载，强制 Referer 头绕过防盗链，支持 Range 续传。"""

    def __init__(self, client: Optional[httpx.Client] = None, timeout: float = 60.0) -> None:
        self._client = client
        self._owns_client = client is None
        self._timeout = timeout

    def download(
        self,
        url: str,
        save_path: str | Path,
        desc: str = "下载",
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> bool:
        """下载 url 到 save_path。

        - 若文件已存在且大小 == Content-Length，跳过并返回 False（已存在，跳过）。
        - 若文件已存在且小于 Content-Length，使用 Range 续传追加。
        - 否则从 0 开始流式下载。
        - 用 tqdm 显示进度条。
        - 任何 HTTP 错误（4xx/5xx）抛 DownloadError。

        返回 True 表示实际下载了内容，False 表示跳过（已完整）。

        若传入 progress_callback，则禁用 tqdm，每写入一个 chunk 后调用
        callback(downloaded_bytes, total_bytes)。
        """
        if self._client is None:
            self._client = httpx.Client(timeout=self._timeout)

        save_path = Path(save_path)

        existing = save_path.stat().st_size if save_path.exists() else 0

        headers = {
            "User-Agent": BROWSER_UA,
            "Referer": "https://www.douyin.com/",
            "Accept": "*/*",
            "Accept-Encoding": "identity",
        }
        if existing > 0:
            headers["Range"] = f"bytes={existing}-"

        try:
            with self._client.stream(
                "GET", url, headers=headers, follow_redirects=True
            ) as response:
                if 400 <= response.status_code:
                    raise DownloadError(f"HTTP {response.status_code} for {url}")

                content_length_header = response.headers.get("Content-Length")
                if content_length_header is None:
                    total = 0
                else:
                    total = int(content_length_header)

                # 服务器忽略 Range 返回 200（完整内容），需截断重写；
                # 206 表示部分内容，追加写入。
                if response.status_code == 206:
                    # 续传：已下载 existing 字节，Content-Length 是剩余部分大小
                    file_mode = "ab"
                    initial = existing
                    # 完整文件总大小 = existing + 剩余
                    display_total = existing + total
                else:
                    # 200（或其他非 206 成功）：服务器返回完整内容
                    file_mode = "wb"
                    initial = 0
                    display_total = total

                # 已完整下载（200 且文件大小 == Content-Length）则跳过
                if (
                    response.status_code == 200
                    and existing > 0
                    and total > 0
                    and existing == total
                ):
                    print("已存在，跳过")
                    return False

                save_path.parent.mkdir(parents=True, exist_ok=True)

                downloaded = initial
                pbar = None
                if progress_callback is None:
                    pbar = tqdm(
                        total=display_total,
                        initial=initial,
                        unit="B",
                        unit_scale=True,
                        desc=desc,
                    )
                try:
                    with open(save_path, file_mode) as f:
                        for chunk in response.iter_bytes(chunk_size=8192):
                            f.write(chunk)
                            downloaded += len(chunk)
                            if pbar is not None:
                                pbar.update(len(chunk))
                            else:
                                progress_callback(downloaded, display_total)
                finally:
                    if pbar is not None:
                        pbar.close()

                return True
        except httpx.HTTPError as exc:
            raise DownloadError(str(exc)) from exc

    def close(self) -> None:
        """如果内部创建了 client，关闭它。"""
        if self._owns_client and self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self):
        if self._client is None:
            self._client = httpx.Client(timeout=self._timeout)
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._owns_client:
            self.close()
