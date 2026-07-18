"""Downloader 单元测试，使用 httpx.MockTransport 模拟网络。"""

from __future__ import annotations

import httpx
import pytest

from douyin_dl.downloader import DownloadError, Downloader


def make_client(handler) -> httpx.Client:
    """构造使用 MockTransport 的 httpx.Client。"""
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_download_new_file(tmp_path):
    """场景 1：新文件下载，200 + 100 字节，返回 True，内容一致。"""
    body = b"a" * 100

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=body,
            headers={"Content-Length": str(len(body))},
        )

    save_path = tmp_path / "video.mp4"
    client = make_client(handler)
    try:
        downloader = Downloader(client=client)
        result = downloader.download("https://example.com/video.mp4", save_path)
    finally:
        client.close()

    assert result is True
    assert save_path.exists()
    assert save_path.read_bytes() == body


def test_download_completes_existing_file(tmp_path):
    """场景 2：文件已完整存在，再次下载应跳过，返回 False，不重写。"""
    body = b"a" * 100
    save_path = tmp_path / "video.mp4"
    save_path.parent.mkdir(parents=True, exist_ok=True)
    save_path.write_bytes(body)  # 预先写入完整内容

    captured_requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        return httpx.Response(
            200,
            content=body,
            headers={"Content-Length": str(len(body))},
        )

    client = make_client(handler)
    try:
        downloader = Downloader(client=client)
        result = downloader.download("https://example.com/video.mp4", save_path)
    finally:
        client.close()

    assert result is False
    # 文件未被重写，内容不变
    assert save_path.read_bytes() == body
    # 确实发起了请求（用于检查 Content-Length）
    assert len(captured_requests) == 1
    # Range 头应已发送（因为文件已存在）
    assert "Range" in captured_requests[0].headers


def test_download_resume_with_range(tmp_path):
    """场景 3：续传，已有 50 字节，服务器返回 206 + 剩余 50 字节，最终 100 字节，返回 True。"""
    existing_part = b"a" * 50
    remaining_part = b"b" * 50
    save_path = tmp_path / "video.mp4"
    save_path.parent.mkdir(parents=True, exist_ok=True)
    save_path.write_bytes(existing_part)

    captured_requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        return httpx.Response(
            206,
            content=remaining_part,
            headers={
                "Content-Length": str(len(remaining_part)),
                "Content-Range": f"bytes 50-99/100",
            },
        )

    client = make_client(handler)
    try:
        downloader = Downloader(client=client)
        result = downloader.download("https://example.com/video.mp4", save_path)
    finally:
        client.close()

    assert result is True
    # 最终文件 = 已有 50 + 新追加 50
    assert save_path.read_bytes() == existing_part + remaining_part
    assert save_path.stat().st_size == 100
    # Range 头应已发送
    assert len(captured_requests) == 1
    assert captured_requests[0].headers.get("Range") == "bytes=50-"


def test_download_403_raises(tmp_path):
    """场景 4：403 响应应抛 DownloadError。"""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, content=b"forbidden")

    save_path = tmp_path / "video.mp4"
    client = make_client(handler)
    try:
        downloader = Downloader(client=client)
        with pytest.raises(DownloadError):
            downloader.download("https://example.com/video.mp4", save_path)
    finally:
        client.close()


def test_download_500_raises(tmp_path):
    """场景 5：500 响应应抛 DownloadError。"""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, content=b"server error")

    save_path = tmp_path / "video.mp4"
    client = make_client(handler)
    try:
        downloader = Downloader(client=client)
        with pytest.raises(DownloadError):
            downloader.download("https://example.com/video.mp4", save_path)
    finally:
        client.close()
