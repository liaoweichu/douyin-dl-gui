"""抖音视频元数据抓取：解析 aweme_id 到 VideoMeta。

优先从分享页 `window._ROUTER_DATA` JSON 提取视频信息，
失败时回退到移动端 `aweme.snssdk.com` 详情接口。
"""

from __future__ import annotations

import json
import re
from typing import Optional

import httpx

from douyin_dl.link_parser import detect_story
from douyin_dl.models import VideoMeta


MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
)

SHARE_VIDEO_URL = "https://www.iesdouyin.com/share/video/{aweme_id}/"
SHARE_NOTE_URL = "https://www.iesdouyin.com/share/note/{aweme_id}/"
MOBILE_DETAIL_URL = "https://aweme.snssdk.com/aweme/v1/aweme/detail/"


class FetcherError(Exception):
    """Raised when both share page and mobile detail fail."""


def _extract_item(router_data: dict) -> Optional[dict]:
    """从 router_data 中按已知嵌套路径定位 aweme item dict。

    依次尝试：
      1. router_data["videoInfoRes"]["item_list"][0]
      2. router_data["loaderData"]["video_(id)/page"]["videoInfoRes"]["item_list"][0]
      3. router_data["item_list"][0]  (顶层兜底)

    找不到或列表为空时返回 None。
    """
    video_info_res = router_data.get("videoInfoRes")
    if isinstance(video_info_res, dict):
        item_list = video_info_res.get("item_list")
        if item_list:
            return item_list[0]

    loader_data = router_data.get("loaderData")
    if isinstance(loader_data, dict):
        page = loader_data.get("video_(id)/page")
        if isinstance(page, dict):
            inner = page.get("videoInfoRes")
            if isinstance(inner, dict):
                item_list = inner.get("item_list")
                if item_list:
                    return item_list[0]

    item_list = router_data.get("item_list")
    if item_list:
        return item_list[0]

    return None


def fetch_share_page(
    aweme_id: str, client: httpx.Client, kind: str = "video"
) -> Optional[dict]:
    """GET the share page (kind='video' or 'note'), extract window._ROUTER_DATA JSON.

    Returns the parsed router_data dict, or None if request fails or JSON missing.
    """
    if kind == "video":
        url = SHARE_VIDEO_URL.format(aweme_id=aweme_id)
    else:
        url = SHARE_NOTE_URL.format(aweme_id=aweme_id)

    headers = {"User-Agent": MOBILE_UA}

    try:
        response = client.get(
            url, headers=headers, follow_redirects=True, timeout=20
        )
    except Exception:
        return None

    if response.status_code != 200:
        return None

    text = response.text

    # 优先查找 window._ROUTER_DATA = ，找不到再回退到 _ROUTER_DATA =
    idx = text.find("window._ROUTER_DATA = ")
    prefix = "window._ROUTER_DATA = "
    if idx == -1:
        idx = text.find("_ROUTER_DATA = ")
        prefix = "_ROUTER_DATA = "
    if idx == -1:
        return None

    start = idx + len(prefix)
    end = text.find("</script>", start)
    if end == -1:
        return None

    raw = text[start:end].strip()
    if raw.endswith(";"):
        raw = raw[:-1].rstrip()

    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return None

    return data if isinstance(data, dict) else None


def extract_play_url(router_data: dict) -> Optional[tuple[str, str, str]]:
    """From router_data, extract (video_url, title, author).

    - video_url: from .video.play_addr.url_list[0], replace '/playwm/' with '/play/'.
    - title: .desc (fallback to share_info.share_title)
    - author: .author.nickname (fallback to .author.unique_id)
    Return None if no play_addr found.
    """
    item = _extract_item(router_data)
    if item is None:
        return None

    play_addr = item.get("video", {}).get("play_addr", {})
    url_list = play_addr.get("url_list", [])
    if not url_list:
        return None

    video_url = url_list[0].replace("/playwm/", "/play/")

    title = item.get("desc") or item.get("share_info", {}).get("share_title") or ""
    author = (
        item.get("author", {}).get("nickname")
        or item.get("author", {}).get("unique_id")
        or ""
    )

    return (video_url, title, author)


def fetch_mobile_detail(aweme_id: str, client: httpx.Client) -> Optional[dict]:
    """GET mobile detail API. Returns the aweme_detail dict (under key 'aweme_detail'),
    or None on failure.

    URL: MOBILE_DETAIL_URL with params aweme_id=<id>, aid=1128.
    Headers: User-Agent = MOBILE_UA.
    """
    params = {"aweme_id": aweme_id, "aid": "1128"}
    headers = {"User-Agent": MOBILE_UA}

    try:
        response = client.get(
            MOBILE_DETAIL_URL, params=params, headers=headers, timeout=20
        )
    except Exception:
        return None

    if response.status_code != 200:
        return None

    try:
        data = response.json()
    except Exception:
        return None

    if not isinstance(data, dict):
        return None

    detail = data.get("aweme_detail")
    return detail if isinstance(detail, dict) else None


def fetch(aweme_id: str, client: httpx.Client) -> VideoMeta:
    """Main entry: build VideoMeta by trying share page first (video kind, then note
    kind), then mobile detail as fallback.

    Sets VideoMeta.is_story / is_24_story / type based on detect_story().
    Sets video_url using extract_play_url logic (replace /playwm/ with /play/).
    Raises FetcherError if all paths fail.
    """
    detail: Optional[dict] = None
    video_url = ""
    title = ""
    author = ""

    # 1. 尝试分享页（先 video 后 note）
    rd = fetch_share_page(aweme_id, client, "video")
    if rd is None:
        rd = fetch_share_page(aweme_id, client, "note")

    # 2. 从分享页提取视频信息
    if rd is not None:
        result = extract_play_url(rd)
        if result is not None:
            video_url, title, author = result
            detail = _extract_item(rd)

    # 3. 分享页失败时回退到移动端详情接口
    if not video_url:
        mobile_detail = fetch_mobile_detail(aweme_id, client)
        if mobile_detail is not None:
            detail = mobile_detail
            play_addr = mobile_detail.get("video", {}).get("play_addr", {})
            url_list = play_addr.get("url_list", [])
            if url_list:
                video_url = url_list[0].replace("/playwm/", "/play/")
            title = mobile_detail.get("desc") or ""
            author = mobile_detail.get("author", {}).get("nickname") or ""

    # 4. 全部失败
    if not video_url:
        raise FetcherError(
            f"无法解析视频 {aweme_id}: 分享页与移动端接口均失败"
        )

    # 5. Story 检测
    if detail is None:
        detail = {}
    is_story = bool(detail.get("is_story"))
    is_24_story = bool(detail.get("is_24_story"))
    type_ = "story" if detect_story(detail) else "normal"

    return VideoMeta(
        aweme_id=aweme_id,
        type=type_,
        title=title,
        author=author,
        video_url=video_url,
        is_story=is_story,
        is_24_story=is_24_story,
    )
