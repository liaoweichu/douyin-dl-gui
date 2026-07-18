"""douyin_dl.pipeline 单元测试，使用 MagicMock 隔离所有外部依赖。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from douyin_dl.browser_fallback import BrowserFallbackError
from douyin_dl.downloader import DownloadError
from douyin_dl.fetcher import FetcherError
from douyin_dl.link_parser import LinkParserError
from douyin_dl.models import Config, VideoMeta
from douyin_dl.pipeline import DownloadPipeline, PipelineStats


# --- 辅助构造 ---------------------------------------------------------------


def _make_config(tmp_path: Path, sleep_range: tuple[float, float] = (0.0, 0.0)) -> Config:
    """构造一个指向 tmp_path 的 Config，sleep_range 默认 (0, 0) 加速测试。"""
    return Config(
        output_dir=tmp_path / "out",
        cookie_path=tmp_path / "cookies.json",
        reauth=False,
        sleep_range=sleep_range,
    )


def _make_cookie_store(cookies=None) -> MagicMock:
    """CookieStore mock：默认返回非空 cookie 列表 + 未过期，避免触发初始 reauth。"""
    cs = MagicMock()
    cs.is_expired.return_value = False
    if cookies is None:
        cookies = [{"name": "sessionid", "value": "abc", "domain": ".douyin.com"}]
    cs.get_cookies.return_value = cookies
    return cs


def _make_video_meta(
    aweme_id: str = "aid1",
    video_url: str = "https://example.com/v.mp4",
) -> VideoMeta:
    return VideoMeta(aweme_id=aweme_id, video_url=video_url, type="normal")


def _make_pipeline(
    config: Config,
    *,
    cookie_store: MagicMock = None,
    auth_bot: MagicMock = None,
    downloader: MagicMock = None,
    fetch_fn=None,
    browser_fallback_fn=None,
) -> DownloadPipeline:
    """统一构造 DownloadPipeline，所有依赖默认为 MagicMock。"""
    return DownloadPipeline(
        config=config,
        cookie_store=cookie_store or _make_cookie_store(),
        auth_bot=auth_bot or MagicMock(),
        downloader=downloader or MagicMock(),
        fetch_fn=fetch_fn,
        browser_fallback_fn=browser_fallback_fn,
    )


# --- Tests ------------------------------------------------------------------


def test_pipeline_stats_init():
    """PipelineStats 初始计数为 0，failed_urls 为空。"""
    stats = PipelineStats()
    assert stats.success == 0
    assert stats.failed == 0
    assert stats.skipped == 0
    assert stats.failed_urls == []


def test_run_all_success(tmp_path):
    """2 个 URL 全部成功：parse + fetch + download 全部正常。"""
    config = _make_config(tmp_path)

    fetch_fn = MagicMock(
        side_effect=[
            _make_video_meta(aweme_id="id1"),
            _make_video_meta(aweme_id="id2"),
        ]
    )
    downloader = MagicMock()
    downloader.download.return_value = True

    pipe = _make_pipeline(config, fetch_fn=fetch_fn, downloader=downloader)

    with patch(
        "douyin_dl.pipeline.parse_input",
        side_effect=[("id1", None), ("id2", None)],
    ):
        stats = pipe.run(["url1", "url2"])

    assert stats.success == 2
    assert stats.failed == 0
    assert stats.skipped == 0
    # 全部成功时不应写 errors.log。
    assert not (config.output_dir / "errors.log").exists()


def test_run_one_skipped_existing(tmp_path):
    """Downloader 返回 False（文件已存在）：计为 skipped。"""
    config = _make_config(tmp_path)

    fetch_fn = MagicMock(return_value=_make_video_meta())
    downloader = MagicMock()
    downloader.download.return_value = False

    pipe = _make_pipeline(config, fetch_fn=fetch_fn, downloader=downloader)

    with patch("douyin_dl.pipeline.parse_input", return_value=("id1", None)):
        stats = pipe.run(["url1"])

    assert stats.skipped == 1
    assert stats.success == 0
    assert stats.failed == 0


def test_run_parse_error_counts_as_failed(tmp_path):
    """parse_input 抛 LinkParserError：计为 failed，写 errors.log。"""
    config = _make_config(tmp_path)

    pipe = _make_pipeline(config)

    with patch(
        "douyin_dl.pipeline.parse_input",
        side_effect=LinkParserError("bad url"),
    ):
        stats = pipe.run(["url1"])

    assert stats.failed == 1
    assert stats.success == 0
    errors_log = config.output_dir / "errors.log"
    assert errors_log.exists()
    content = errors_log.read_text(encoding="utf-8")
    assert "url1" in content


def test_errors_log_format(tmp_path):
    """errors.log 格式：单行、以 [ISO timestamp] 开头、含 url 与 reason。"""
    config = _make_config(tmp_path)

    pipe = _make_pipeline(config)

    url = "https://v.douyin.com/xxx/"
    with patch(
        "douyin_dl.pipeline.parse_input",
        side_effect=LinkParserError("test reason"),
    ):
        stats = pipe.run([url])

    assert stats.failed == 1
    errors_log = config.output_dir / "errors.log"
    assert errors_log.exists()
    content = errors_log.read_text(encoding="utf-8")
    lines = content.splitlines()
    # 单行。
    assert len(lines) == 1
    line = lines[0]
    # 以 [ 开头（ISO 时间戳在方括号内）。
    assert line.startswith("[")
    # 含 URL。
    assert url in line
    # 含 "test reason"。
    assert "test reason" in line


def test_run_fetch_error_triggers_browser_fallback_success(tmp_path):
    """fetch_fn 抛 FetcherError，注入的 browser_fallback_fn 成功返回 URL。"""
    config = _make_config(tmp_path)

    fetch_fn = MagicMock(side_effect=FetcherError("fail"))
    fallback_fn = MagicMock(return_value="https://example.com/fallback.mp4")
    downloader = MagicMock()
    downloader.download.return_value = True

    pipe = _make_pipeline(
        config,
        fetch_fn=fetch_fn,
        browser_fallback_fn=fallback_fn,
        downloader=downloader,
    )

    with patch("douyin_dl.pipeline.parse_input", return_value=("id1", None)):
        stats = pipe.run(["url1"])

    assert stats.success == 1
    assert stats.failed == 0
    fallback_fn.assert_called_once()
    # 第一次调用应以 kind="video" 进行。
    assert fallback_fn.call_args.args[2] == "video"


def test_run_fetch_error_browser_fallback_both_kinds_fail(tmp_path):
    """fetch_fn 抛 FetcherError，browser_fallback_fn 在 video 和 note 两种 kind 上都失败。"""
    config = _make_config(tmp_path)

    fetch_fn = MagicMock(side_effect=FetcherError("fail"))
    fallback_fn = MagicMock(side_effect=BrowserFallbackError("nope"))
    downloader = MagicMock()

    pipe = _make_pipeline(
        config,
        fetch_fn=fetch_fn,
        browser_fallback_fn=fallback_fn,
        downloader=downloader,
    )

    with patch("douyin_dl.pipeline.parse_input", return_value=("id1", None)):
        stats = pipe.run(["url1"])

    assert stats.failed == 1
    assert stats.success == 0
    # 两种 kind 都应被尝试过。
    assert fallback_fn.call_count == 2
    kinds_called = [call.args[2] for call in fallback_fn.call_args_list]
    assert kinds_called == ["video", "note"]
    # 兜底失败后不应触达 Downloader。
    downloader.download.assert_not_called()


def test_run_download_401_triggers_reauth_and_retry(tmp_path):
    """Downloader 首次抛 DownloadError("HTTP 403")：触发 reauth + 重试，第二次返回 True。"""
    config = _make_config(tmp_path)

    fetch_fn = MagicMock(return_value=_make_video_meta())
    downloader = MagicMock()
    downloader.download.side_effect = [DownloadError("HTTP 403"), True]
    auth_bot = MagicMock()

    pipe = _make_pipeline(
        config,
        fetch_fn=fetch_fn,
        downloader=downloader,
        auth_bot=auth_bot,
    )

    with patch("douyin_dl.pipeline.parse_input", return_value=("id1", None)):
        stats = pipe.run(["url1"])

    assert stats.success == 1
    assert stats.failed == 0
    # 仅在 403 重试时调用一次 login（初始 cookie 非空，不触发初始 reauth）。
    auth_bot.login.assert_called_once()
    # Downloader 应被调用 2 次（首次失败 + 重试成功）。
    assert downloader.download.call_count == 2


def test_run_download_401_retry_still_fails(tmp_path):
    """Downloader 始终抛 DownloadError("HTTP 401")：reauth 后重试仍失败，计为 failed。"""
    config = _make_config(tmp_path)

    fetch_fn = MagicMock(return_value=_make_video_meta())
    downloader = MagicMock()
    downloader.download.side_effect = DownloadError("HTTP 401")
    auth_bot = MagicMock()

    pipe = _make_pipeline(
        config,
        fetch_fn=fetch_fn,
        downloader=downloader,
        auth_bot=auth_bot,
    )

    with patch("douyin_dl.pipeline.parse_input", return_value=("id1", None)):
        stats = pipe.run(["url1"])

    assert stats.failed == 1
    assert stats.success == 0


def test_run_download_500_no_reauth(tmp_path):
    """Downloader 抛 DownloadError("HTTP 500")：不触发 reauth，直接计为 failed。"""
    config = _make_config(tmp_path)

    fetch_fn = MagicMock(return_value=_make_video_meta())
    downloader = MagicMock()
    downloader.download.side_effect = DownloadError("HTTP 500")
    auth_bot = MagicMock()

    pipe = _make_pipeline(
        config,
        fetch_fn=fetch_fn,
        downloader=downloader,
        auth_bot=auth_bot,
    )

    with patch("douyin_dl.pipeline.parse_input", return_value=("id1", None)):
        stats = pipe.run(["url1"])

    assert stats.failed == 1
    assert stats.success == 0
    # 500 错误不应触发 reauth。
    auth_bot.login.assert_not_called()
    # 500 错误也不应重试，Downloader 只被调用一次。
    downloader.download.assert_called_once()


def test_run_sleeps_between_items(tmp_path):
    """3 个 URL 应在条目间 sleep 2 次（最后一个不 sleep）。"""
    config = _make_config(tmp_path)

    fetch_fn = MagicMock(return_value=_make_video_meta())
    downloader = MagicMock()
    downloader.download.return_value = True

    pipe = _make_pipeline(config, fetch_fn=fetch_fn, downloader=downloader)

    with patch("douyin_dl.pipeline.parse_input", return_value=("id1", None)):
        with patch("douyin_dl.pipeline.time") as mock_time:
            stats = pipe.run(["url1", "url2", "url3"])

    # 3 个条目 → 2 次 sleep（最后一个不 sleep）。
    assert mock_time.sleep.call_count == 2
    assert stats.success == 3


def test_run_summary_printed(tmp_path, capsys):
    """运行结束后 stdout 应包含 "完成：成功" 及正确计数。"""
    config = _make_config(tmp_path)

    fetch_fn = MagicMock(return_value=_make_video_meta())
    downloader = MagicMock()
    downloader.download.return_value = True

    pipe = _make_pipeline(config, fetch_fn=fetch_fn, downloader=downloader)

    with patch("douyin_dl.pipeline.parse_input", return_value=("id1", None)):
        pipe.run(["url1", "url2"])

    captured = capsys.readouterr()
    assert "完成：成功" in captured.out
    assert "完成：成功 2 条，失败 0 条，跳过 0 条" in captured.out
