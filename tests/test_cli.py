"""douyin_dl.cli 单元测试。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from douyin_dl.cli import LinkCollector, main, parse_args
from douyin_dl.pipeline import PipelineStats


# --- LinkCollector ----------------------------------------------------------


def test_link_collector_pure_urls():
    """仅传入 urls 列表，原样返回（去重后）。"""
    assert LinkCollector.collect(["url1", "url2"], None, None) == ["url1", "url2"]


def test_link_collector_from_file(tmp_path):
    """从文件读取链接，每行一条。"""
    f = tmp_path / "links.txt"
    f.write_text("url1\nurl2\n", encoding="utf-8")
    assert LinkCollector.collect([], str(f), None) == ["url1", "url2"]


def test_link_collector_from_stdin():
    """从 stdin 文本读取链接。"""
    assert LinkCollector.collect([], None, "url1\nurl2\n") == ["url1", "url2"]


def test_link_collector_merges_all_three(tmp_path):
    """三个来源合并：urls + file + stdin。"""
    f = tmp_path / "links.txt"
    f.write_text("b\n", encoding="utf-8")
    assert LinkCollector.collect(["a"], str(f), "c\n") == ["a", "b", "c"]


def test_link_collector_dedup_preserves_order():
    """去重时保留首次出现的顺序。"""
    assert LinkCollector.collect(["a", "b", "a", "c"], None, None) == [
        "a",
        "b",
        "c",
    ]


def test_link_collector_skips_empty_and_comments(tmp_path):
    """跳过空行、注释行，并去除每行首尾空白。"""
    f = tmp_path / "links.txt"
    f.write_text(
        "# comment\n\nurl1\n  url2  \n# another\nurl3",
        encoding="utf-8",
    )
    assert LinkCollector.collect([], str(f), None) == ["url1", "url2", "url3"]


def test_link_collector_empty_inputs():
    """所有来源均为空时返回空列表。"""
    assert LinkCollector.collect([], None, None) == []


# --- parse_args -------------------------------------------------------------


def test_parse_args_defaults():
    """无参数时使用默认值。"""
    args, config = parse_args([])
    assert config.output_dir == Path("./downloads")
    assert config.quality == "default"
    assert config.reauth is False
    assert args.urls == []
    assert args.file is None


def test_parse_args_output_override():
    """-o 覆盖输出目录。"""
    args, config = parse_args(["-o", "/tmp/x"])
    assert config.output_dir == Path("/tmp/x")


def test_parse_args_reauth_flag():
    """--reauth 设置 reauth=True。"""
    args, config = parse_args(["--reauth"])
    assert config.reauth is True


def test_parse_args_quality_choice():
    """--quality 接受合法值；非法值触发 SystemExit。"""
    args, config = parse_args(["--quality", "1080p"])
    assert config.quality == "1080p"

    with pytest.raises(SystemExit):
        parse_args(["--quality", "4k"])


def test_parse_args_file():
    """-f 设置 file 路径。"""
    args, config = parse_args(["-f", "links.txt"])
    assert args.file == "links.txt"


# --- main -------------------------------------------------------------------


def _patch_deps(monkeypatch, stats: PipelineStats | None = None) -> MagicMock:
    """把 cli 模块里的 CookieStore / AuthBot / DownloadPipeline 全部替换为 MagicMock。

    返回 DownloadPipeline 的 mock 类，便于断言 run 调用。
    """
    monkeypatch.setattr("douyin_dl.cli.CookieStore", MagicMock())
    monkeypatch.setattr("douyin_dl.cli.AuthBot", MagicMock())
    mock_pipeline_cls = MagicMock()
    if stats is None:
        stats = PipelineStats()
    mock_pipeline_cls.return_value.run.return_value = stats
    monkeypatch.setattr("douyin_dl.cli.DownloadPipeline", mock_pipeline_cls)
    return mock_pipeline_cls


def _make_tty_stdin() -> MagicMock:
    """构造一个 isatty() 返回 True 的假 stdin（模拟终端，不消费 stdin）。"""
    fake = MagicMock()
    fake.isatty.return_value = True
    return fake


def test_main_no_urls_returns_2(monkeypatch, capsys):
    """无链接且无 stdin 时返回 2，并向 stderr 打印用法。"""
    monkeypatch.setattr("sys.stdin", _make_tty_stdin())
    _patch_deps(monkeypatch)

    result = main([])

    assert result == 2
    captured = capsys.readouterr()
    assert "用法" in captured.err


def test_main_runs_pipeline(monkeypatch, capsys):
    """有链接时调用 pipeline.run 并返回 0，stdout 包含链接计数。"""
    monkeypatch.setattr("sys.stdin", _make_tty_stdin())
    stats = PipelineStats()
    stats.success = 2
    stats.failed = 0
    stats.skipped = 0
    mock_pipeline_cls = _patch_deps(monkeypatch, stats=stats)

    result = main(["url1", "url2"])

    assert result == 0
    captured = capsys.readouterr()
    assert "共 2 条链接待下载" in captured.out
    mock_pipeline_cls.return_value.run.assert_called_once_with(["url1", "url2"])


def test_main_reads_stdin_when_not_tty(monkeypatch):
    """stdin 非 TTY 时读取其内容作为链接来源。"""
    fake_stdin = MagicMock()
    fake_stdin.isatty.return_value = False
    fake_stdin.read.return_value = "url1\nurl2\n"
    monkeypatch.setattr("sys.stdin", fake_stdin)
    mock_pipeline_cls = _patch_deps(monkeypatch)

    main([])

    mock_pipeline_cls.return_value.run.assert_called_once_with(["url1", "url2"])
