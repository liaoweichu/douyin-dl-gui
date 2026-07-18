"""douyin_dl.fetcher 单元测试，使用 httpx.MockTransport 模拟网络。"""

from __future__ import annotations

import json

import httpx
import pytest

from douyin_dl.fetcher import (
    FetcherError,
    extract_play_url,
    fetch,
    fetch_mobile_detail,
    fetch_share_page,
)
from douyin_dl.models import VideoMeta


# --- 辅助构造 ---------------------------------------------------------------


def share_page_html(router_data: dict) -> str:
    """构造包含 window._ROUTER_DATA 赋值的分享页 HTML。"""
    return f"<html><script>window._ROUTER_DATA = {json.dumps(router_data)}</script></html>"


def make_client(handler) -> httpx.Client:
    """构造使用 MockTransport 的 httpx.Client。"""
    return httpx.Client(transport=httpx.MockTransport(handler))


def make_item(
    aweme_id: str = "7001234567890",
    desc: str = "测试视频",
    nickname: str = "测试作者",
    play_url: str = "https://example.com/playwm/video.mp4",
    is_story: int = 0,
    is_24_story: int = 0,
) -> dict:
    """构造一个 aweme item dict，包含视频/作者/Story 字段。"""
    return {
        "aweme_id": aweme_id,
        "desc": desc,
        "author": {"nickname": nickname, "unique_id": "test_uid"},
        "video": {
            "play_addr": {
                "url_list": [play_url],
            },
        },
        "share_info": {"share_title": "分享标题"},
        "is_story": is_story,
        "is_24_story": is_24_story,
    }


# --- fetch_share_page -------------------------------------------------------


def test_fetch_share_page_success():
    """场景 1：HTML 含 window._ROUTER_DATA JSON，返回解析后的 dict。"""
    router_data = {"videoInfoRes": {"item_list": [make_item()]}}
    html = share_page_html(router_data)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html)

    client = make_client(handler)
    try:
        result = fetch_share_page("7001234567890", client, "video")
        assert result == router_data
    finally:
        client.close()


def test_fetch_share_page_missing_router_data():
    """场景 2：HTML 不含 _ROUTER_DATA，返回 None。"""
    html = "<html><body>no router data here</body></html>"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html)

    client = make_client(handler)
    try:
        assert fetch_share_page("7001234567890", client, "video") is None
    finally:
        client.close()


def test_fetch_share_page_network_error():
    """场景 3：网络异常（ConnectError），返回 None。"""
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client = make_client(handler)
    try:
        assert fetch_share_page("7001234567890", client, "video") is None
    finally:
        client.close()


# --- extract_play_url -------------------------------------------------------


def test_extract_play_url_full_path():
    """场景 4：videoInfoRes.item_list[0] 路径，返回 /play/ 而非 /playwm/。"""
    router_data = {
        "videoInfoRes": {
            "item_list": [
                {
                    "desc": "hello",
                    "author": {"nickname": "Alice"},
                    "video": {
                        "play_addr": {
                            "url_list": ["https://example.com/playwm/x.mp4"],
                        },
                    },
                }
            ]
        }
    }
    result = extract_play_url(router_data)
    assert result is not None
    video_url, title, author = result
    assert video_url == "https://example.com/play/x.mp4"
    assert "/playwm/" not in video_url
    assert title == "hello"
    assert author == "Alice"


def test_extract_play_url_loader_data_path():
    """场景 5：loaderData 嵌套路径，返回正确 tuple。"""
    router_data = {
        "loaderData": {
            "video_(id)/page": {
                "videoInfoRes": {
                    "item_list": [
                        {
                            "desc": "loader",
                            "author": {"nickname": "Bob"},
                            "video": {
                                "play_addr": {
                                    "url_list": [
                                        "https://example.com/playwm/y.mp4"
                                    ],
                                },
                            },
                        }
                    ]
                }
            }
        }
    }
    result = extract_play_url(router_data)
    assert result is not None
    video_url, title, author = result
    assert video_url == "https://example.com/play/y.mp4"
    assert title == "loader"
    assert author == "Bob"


def test_extract_play_url_empty_url_list():
    """场景 6：url_list 为空，返回 None。"""
    router_data = {
        "videoInfoRes": {
            "item_list": [
                {
                    "desc": "hello",
                    "author": {"nickname": "Alice"},
                    "video": {"play_addr": {"url_list": []}},
                }
            ]
        }
    }
    assert extract_play_url(router_data) is None


def test_extract_play_url_missing_play_addr():
    """场景 7：无 play_addr 键，返回 None。"""
    router_data = {
        "videoInfoRes": {
            "item_list": [
                {
                    "desc": "hello",
                    "author": {"nickname": "Alice"},
                    "video": {},
                }
            ]
        }
    }
    assert extract_play_url(router_data) is None


# --- fetch_mobile_detail ----------------------------------------------------


def test_fetch_mobile_detail_success():
    """场景 8：返回 {"aweme_detail": {...}}，提取内层 detail dict。"""
    detail = {
        "aweme_id": "7001234567890",
        "desc": "mobile",
        "author": {"nickname": "MobileAuthor"},
        "video": {
            "play_addr": {
                "url_list": ["https://example.com/playwm/m.mp4"],
            },
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/aweme/v1/aweme/detail/"
        assert request.url.params["aweme_id"] == "7001234567890"
        assert request.url.params["aid"] == "1128"
        return httpx.Response(200, json={"aweme_detail": detail})

    client = make_client(handler)
    try:
        result = fetch_mobile_detail("7001234567890", client)
        assert result == detail
    finally:
        client.close()


def test_fetch_mobile_detail_404():
    """场景 9：404 响应，返回 None。"""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="not found")

    client = make_client(handler)
    try:
        assert fetch_mobile_detail("7001234567890", client) is None
    finally:
        client.close()


# --- fetch (集成) -----------------------------------------------------------


def test_fetch_normal_video_via_share_page():
    """场景 10：分享页返回普通视频，type=normal，video_url 含 /play/。"""
    item = make_item(
        desc="普通视频",
        nickname="普通作者",
        play_url="https://example.com/playwm/normal.mp4",
        is_story=0,
        is_24_story=0,
    )
    router_data = {"videoInfoRes": {"item_list": [item]}}
    html = share_page_html(router_data)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html)

    client = make_client(handler)
    try:
        meta = fetch("7001234567890", client)
        assert isinstance(meta, VideoMeta)
        assert meta.aweme_id == "7001234567890"
        assert meta.type == "normal"
        assert meta.video_url == "https://example.com/play/normal.mp4"
        assert "/playwm/" not in meta.video_url
        assert meta.title == "普通视频"
        assert meta.author == "普通作者"
        assert meta.is_story is False
        assert meta.is_24_story is False
    finally:
        client.close()


def test_fetch_story_video_via_share_page():
    """场景 11：分享页返回 is_story=1 的视频，type=story，is_story=True。"""
    item = make_item(
        desc="Story 视频",
        nickname="Story 作者",
        play_url="https://example.com/playwm/story.mp4",
        is_story=1,
        is_24_story=0,
    )
    router_data = {"videoInfoRes": {"item_list": [item]}}
    html = share_page_html(router_data)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html)

    client = make_client(handler)
    try:
        meta = fetch("7001234567890", client)
        assert meta.type == "story"
        assert meta.is_story is True
        assert meta.is_24_story is False
        assert meta.video_url == "https://example.com/play/story.mp4"
    finally:
        client.close()


def test_fetch_fallback_to_mobile_detail():
    """场景 12：分享页 404，回退到移动端详情接口成功。"""
    detail = {
        "aweme_id": "7001234567890",
        "desc": "mobile detail",
        "author": {"nickname": "MobileAuthor"},
        "video": {
            "play_addr": {
                "url_list": ["https://example.com/playwm/mobile.mp4"],
            },
        },
        "is_story": 0,
        "is_24_story": 0,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.startswith("/share/video/") or path.startswith("/share/note/"):
            return httpx.Response(404, text="not found")
        if path == "/aweme/v1/aweme/detail/":
            return httpx.Response(200, json={"aweme_detail": detail})
        return httpx.Response(404)

    client = make_client(handler)
    try:
        meta = fetch("7001234567890", client)
        assert meta.aweme_id == "7001234567890"
        assert meta.video_url == "https://example.com/play/mobile.mp4"
        assert meta.title == "mobile detail"
        assert meta.author == "MobileAuthor"
        assert meta.type == "normal"
    finally:
        client.close()


def test_fetch_all_fail_raises():
    """场景 13：分享页（video+note）与移动端接口均失败，抛 FetcherError。"""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="not found")

    client = make_client(handler)
    try:
        with pytest.raises(FetcherError):
            fetch("7001234567890", client)
    finally:
        client.close()
