"""抖音分享链接解析：提取短链、跟随重定向拿 aweme_id、判断日常/Story 视频。"""

from __future__ import annotations

import re
from typing import Optional

import httpx


# 移动端 Safari UA，访问短链与移动端接口时使用。
MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/16.6 Mobile/15E148 Safari/604.1"
)

# Regex to find Douyin short URLs in arbitrary text.
SHORT_URL_RE = re.compile(r"https?://v\.douyin\.com/[A-Za-z0-9_-]+/?")

# Regex to extract aweme_id from a resolved URL (after following redirects).
# Matches /video/<id>, /note/<id>, /share/video/<id>, /share/note/<id>.
AWEME_ID_RE = re.compile(r"/(?:share/)?(?:video|note)/(\d+)")

# Regex to recognize a bare aweme_id input (just digits, 8+).
AWEME_ID_ONLY_RE = re.compile(r"^\d{8,}$")


class LinkParserError(Exception):
    """Raised when input cannot be parsed into an aweme_id."""


def extract_short_url(text: str) -> str:
    """Find the first Douyin short URL in arbitrary text (e.g. share command text).

    Raises LinkParserError if none found.
    """
    text = text.strip()
    match = SHORT_URL_RE.search(text)
    if not match:
        raise LinkParserError("未找到短链")
    return match.group(0)


def resolve_aweme_id(short_url: str, client: "httpx.Client | None" = None) -> str:
    """Follow redirects on a short URL to get the final URL, then extract aweme_id.

    Accepts an optional httpx.Client (or httpx.BaseClient). If None, creates a new
    httpx.Client with a mobile UA, follows redirects, then closes.
    Raises LinkParserError if redirect fails to yield an aweme_id.
    """
    if client is None:
        client = httpx.Client(
            headers={"User-Agent": MOBILE_UA}, follow_redirects=True
        )
        try:
            response = client.get(short_url)
        finally:
            client.close()
    else:
        response = client.get(short_url)

    match = AWEME_ID_RE.search(str(response.url))
    if not match:
        raise LinkParserError(f"无法从跳转 URL 解析 aweme_id: {response.url}")
    return match.group(1)


def detect_story(detail: dict) -> bool:
    """Return True if the aweme detail dict indicates a Story/日常 video.

    Checks:
      - detail.get("is_story") truthy, OR
      - detail.get("is_24_story") truthy, OR
      - detail.get("filter_list", [{}])[0].get("filter_reason") == "story_25_filter"
        (also matches if "story" appears in the filter_reason string)
    """
    if detail.get("is_story"):
        return True
    if detail.get("is_24_story"):
        return True

    filter_list = detail.get("filter_list") or []
    if filter_list:
        reason = filter_list[0].get("filter_reason")
        if reason is not None and (reason == "story_25_filter" or "story" in str(reason)):
            return True
    return False


def parse_input(text: str, client: "httpx.Client | None" = None) -> tuple[str, Optional[str]]:
    """Convenience: take any user input (bare aweme_id, short URL, or share command text),
    return (aweme_id, short_url_or_None).

    - If input is a bare aweme_id (matches AWEME_ID_ONLY_RE), return (id, None).
    - Otherwise extract short URL via extract_short_url, resolve via resolve_aweme_id,
      return (aweme_id, short_url).
    """
    stripped = text.strip()
    if AWEME_ID_ONLY_RE.fullmatch(stripped):
        return (stripped, None)
    short_url = extract_short_url(text)
    aweme_id = resolve_aweme_id(short_url, client=client)
    return (aweme_id, short_url)
