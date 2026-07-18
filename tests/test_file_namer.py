"""douyin_dl.file_namer 单元测试。"""

from __future__ import annotations

from pathlib import Path

from douyin_dl.file_namer import FileNamer, MAX_FILENAME_LENGTH
from douyin_dl.models import VideoMeta


# --- sanitize_component ---------------------------------------------------


def test_sanitize_normal_chinese():
    assert FileNamer.sanitize_component("张三", "fallback") == "张三"


def test_sanitize_illegal_chars_replaced():
    assert FileNamer.sanitize_component("hello/world:foo", "fallback") == "hello_world_foo"


def test_sanitize_control_chars_replaced():
    assert FileNamer.sanitize_component("hello\x00world\x01foo", "fallback") == "hello_world_foo"


def test_sanitize_strips_leading_trailing_dots():
    assert FileNamer.sanitize_component("...hello...", "fallback") == "hello"


def test_sanitize_collapses_multiple_underscores():
    assert FileNamer.sanitize_component("a___b", "fallback") == "a_b"


def test_sanitize_empty_returns_fallback():
    assert FileNamer.sanitize_component("", "fallback") == "fallback"


def test_sanitize_none_returns_fallback():
    assert FileNamer.sanitize_component(None, "fallback") == "fallback"


def test_sanitize_only_illegal_returns_fallback():
    assert FileNamer.sanitize_component("/?:*", "fallback") == "fallback"


# --- build ----------------------------------------------------------------


def test_build_normal():
    meta = VideoMeta(aweme_id="1234567890", author="张三", title="今天天气真好")
    path = FileNamer.build(meta, Path("./downloads"))
    assert path.name == "张三_今天天气真好_1234567890.mp4"
    assert path.parent == Path("./downloads")


def test_build_missing_author():
    meta = VideoMeta(aweme_id="123", author="", title="hello")
    path = FileNamer.build(meta, Path("./downloads"))
    assert path.name == "unknown_hello_123.mp4"


def test_build_missing_title():
    meta = VideoMeta(aweme_id="123", author="alice", title="")
    path = FileNamer.build(meta, Path("./downloads"))
    assert path.name == "alice_untitled_123.mp4"


def test_build_missing_both():
    meta = VideoMeta(aweme_id="123")
    path = FileNamer.build(meta, Path("./downloads"))
    assert path.name == "unknown_untitled_123.mp4"


def test_build_title_with_illegal_chars():
    meta = VideoMeta(aweme_id="123", title="hello/world:foo")
    path = FileNamer.build(meta, Path("./downloads"))
    assert path.name == "unknown_hello_world_foo_123.mp4"


def test_build_truncates_long_title():
    meta = VideoMeta(aweme_id="123", author="a", title="x" * 200)
    path = FileNamer.build(meta, Path("./downloads"))
    stem = path.stem
    assert len(stem) <= MAX_FILENAME_LENGTH
    assert stem.endswith("_123")


def test_build_output_dir_str_coerced():
    meta = VideoMeta(aweme_id="123")
    path = FileNamer.build(meta, "./downloads")
    assert path.parent == Path("./downloads")
    assert path.name == "unknown_untitled_123.mp4"


def test_build_does_not_create_dir(tmp_path):
    output_dir = tmp_path / "downloads"
    meta = VideoMeta(aweme_id="123")
    FileNamer.build(meta, output_dir)
    assert not output_dir.exists()
