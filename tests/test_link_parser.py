"""douyin_dl.link_parser 单元测试。"""

from __future__ import annotations

import httpx
import pytest

from douyin_dl.link_parser import (
    LinkParserError,
    detect_story,
    extract_short_url,
    parse_input,
    resolve_aweme_id,
)


def make_client_redirect(short_url: str, final_url: str) -> httpx.Client:
    """构造一个 MockTransport 客户端：对 short_url 返回 302 到 final_url，
    对其它 URL（即 final_url 本身）返回 200，配合 follow_redirects=True 模拟跳转。
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url == short_url:
            return httpx.Response(302, headers={"location": final_url})
        return httpx.Response(200)

    return httpx.Client(
        transport=httpx.MockTransport(handler), follow_redirects=True
    )


# --- extract_short_url -----------------------------------------------------


def test_extract_short_url_from_pure_link():
    url = "https://v.douyin.com/abc123/"
    assert extract_short_url(url) == url


def test_extract_short_url_from_share_text():
    text = "7.99 复制打开抖音，看看【XXX的作品】https://v.douyin.com/abc123/"
    assert extract_short_url(text) == "https://v.douyin.com/abc123/"


def test_extract_short_url_not_found_raises():
    with pytest.raises(LinkParserError):
        extract_short_url("hello world")


# --- resolve_aweme_id ------------------------------------------------------


def test_resolve_aweme_id_video():
    short_url = "https://v.douyin.com/abc123/"
    final_url = "https://www.iesdouyin.com/share/video/7001234567890/"
    client = make_client_redirect(short_url, final_url)
    try:
        assert resolve_aweme_id(short_url, client=client) == "7001234567890"
    finally:
        client.close()


def test_resolve_aweme_id_note():
    short_url = "https://v.douyin.com/abc123/"
    final_url = "https://www.douyin.com/note/7009876543210"
    client = make_client_redirect(short_url, final_url)
    try:
        assert resolve_aweme_id(short_url, client=client) == "7009876543210"
    finally:
        client.close()


def test_resolve_aweme_id_no_match_raises():
    short_url = "https://v.douyin.com/abc123/"
    final_url = "https://example.com/foo"
    client = make_client_redirect(short_url, final_url)
    try:
        with pytest.raises(LinkParserError):
            resolve_aweme_id(short_url, client=client)
    finally:
        client.close()


# --- detect_story ----------------------------------------------------------


def test_detect_story_is_story():
    assert detect_story({"is_story": 1}) is True


def test_detect_story_is_24_story():
    assert detect_story({"is_24_story": True}) is True


def test_detect_story_filter_list():
    assert detect_story({"filter_list": [{"filter_reason": "story_25_filter"}]}) is True


def test_detect_story_filter_substring():
    assert detect_story({"filter_list": [{"filter_reason": "story_xx"}]}) is True


def test_detect_story_normal():
    assert detect_story({"is_story": 0, "is_24_story": False}) is False


def test_detect_story_empty_filter_list():
    assert detect_story({"filter_list": []}) is False


def test_detect_story_no_filter_list_key():
    assert detect_story({}) is False


# --- parse_input -----------------------------------------------------------


def test_parse_input_bare_aweme_id():
    assert parse_input("7001234567890") == ("7001234567890", None)


def test_parse_input_short_url():
    short_url = "https://v.douyin.com/abc/"
    final_url = "https://www.iesdouyin.com/share/video/7001234567890/"
    client = make_client_redirect(short_url, final_url)
    try:
        assert parse_input(short_url, client=client) == (
            "7001234567890",
            "https://v.douyin.com/abc/",
        )
    finally:
        client.close()
