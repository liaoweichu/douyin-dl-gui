from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from douyin_dl.cookie_store import CookieStore


def test_load_missing_file_returns_none(tmp_path: Path) -> None:
    """load on non-existent path returns None."""
    store = CookieStore(tmp_path / "missing.json")
    assert store.load() is None


def test_save_then_load_roundtrip(tmp_path: Path) -> None:
    """save some cookies, load back, fields match."""
    cookie_path = tmp_path / "cookies.json"
    store = CookieStore(cookie_path)

    cookies = [
        {"name": "sessionid", "value": "abc123", "domain": ".douyin.com"},
        {"name": "ttwid", "value": "xyz789", "domain": ".douyin.com"},
    ]
    ts = 1_700_000_000.0
    store.save(cookies, ts=ts)

    loaded = store.load()
    assert loaded is not None
    assert loaded["cookies"] == cookies
    assert loaded["fetched_at"] == ts


def test_save_creates_parent_dir(tmp_path: Path) -> None:
    """save to a path whose parent doesn't exist; parent dir created."""
    nested = tmp_path / "a" / "b" / "c" / "cookies.json"
    store = CookieStore(nested)

    store.save([{"name": "k", "value": "v"}], ts=1.0)

    assert nested.parent.exists()
    assert nested.exists()
    # 内容可被正确读回。
    loaded = store.load()
    assert loaded is not None
    assert loaded["cookies"] == [{"name": "k", "value": "v"}]


def test_is_expired_when_file_missing(tmp_path: Path) -> None:
    """True for missing file."""
    store = CookieStore(tmp_path / "missing.json")
    assert store.is_expired() is True


def test_is_expired_when_fresh(tmp_path: Path) -> None:
    """False immediately after save."""
    store = CookieStore(tmp_path / "cookies.json")
    store.save([{"name": "k", "value": "v"}])
    assert store.is_expired(max_age=86400) is False


def test_is_expired_when_old(tmp_path: Path) -> None:
    """True if fetched_at is more than max_age seconds in the past."""
    store = CookieStore(tmp_path / "cookies.json")
    # 用一个小 max_age（1 秒），写入后睡 1.1 秒，应当判定过期。
    store.save([{"name": "k", "value": "v"}])
    time.sleep(1.1)
    assert store.is_expired(max_age=1) is True


def test_clear_removes_file(tmp_path: Path) -> None:
    """clear after save → file gone; clear on missing file → no error."""
    cookie_path = tmp_path / "cookies.json"
    store = CookieStore(cookie_path)

    store.save([{"name": "k", "value": "v"}], ts=1.0)
    assert cookie_path.exists()

    store.clear()
    assert not cookie_path.exists()

    # 文件已不存在时再 clear 不应报错。
    store.clear()


def test_get_cookies_missing_file(tmp_path: Path) -> None:
    """returns empty list when file doesn't exist."""
    store = CookieStore(tmp_path / "missing.json")
    assert store.get_cookies() == []


def test_load_corrupt_file_returns_none(tmp_path: Path) -> None:
    """损坏的 JSON 文件 load 返回 None。"""
    cookie_path = tmp_path / "corrupt.json"
    cookie_path.write_text("{not valid json", encoding="utf-8")

    store = CookieStore(cookie_path)
    assert store.load() is None
    # get_cookies 在损坏时也应返回空列表。
    assert store.get_cookies() == []
