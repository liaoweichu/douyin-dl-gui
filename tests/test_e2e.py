"""端到端冒烟测试（全部 mock，无真实网络/Playwright）。

覆盖 parse → fetch → (browser fallback) → download 完整流转，
3 个 URL 分别命中 success / failed / skipped 三种结局。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from douyin_dl.browser_fallback import BrowserFallbackError
from douyin_dl.fetcher import FetcherError
from douyin_dl.models import Config, VideoMeta
from douyin_dl.pipeline import DownloadPipeline


URLS = [
    "https://v.douyin.com/aaa/",
    "https://v.douyin.com/bbb/",
    "https://v.douyin.com/ccc/",
]


def _parse_side_effect(url, client=None):
    """根据 URL 返回对应 aweme_id。"""
    if "aaa" in url:
        return ("aaa_id", None)
    if "bbb" in url:
        return ("bbb_id", None)
    if "ccc" in url:
        return ("ccc_id", None)
    raise AssertionError(f"unexpected url: {url}")


def _fetch_side_effect(aweme_id, client):
    """bbb_id 抛 FetcherError 触发浏览器兜底；其余返回 VideoMeta。"""
    if aweme_id == "bbb_id":
        raise FetcherError("fetch failed for bbb")
    return VideoMeta(
        aweme_id=aweme_id,
        video_url="https://example.com/v.mp4",
        author="tester",
        title="hello",
    )


def _browser_fallback_fn(aweme_id, cookies, kind):
    """两种 kind 都抛 BrowserFallbackError。"""
    raise BrowserFallbackError("nope")


def test_e2e_three_urls_two_success_one_failure(tmp_path, capsys):
    """端到端：3 URL → 1 success (aaa) + 1 failed (bbb) + 1 skipped (ccc)。"""
    config = Config(output_dir=tmp_path, sleep_range=(0.0, 0.0))

    cookie_store = MagicMock()
    cookie_store.is_expired.return_value = False
    # 非空 cookies 列表：避免触发初始 _reauth → auth_bot.login 被调用。
    # 任务说明中 get_cookies.return_value=[] 与 "auth_bot 不被调用" 互相矛盾，
    # 此处采用非空列表以匹配 "auth_bot 不会被调用" 的要求。
    cookie_store.get_cookies.return_value = [
        {"name": "sessionid", "value": "abc", "domain": ".douyin.com"}
    ]

    auth_bot = MagicMock()
    # 即便意外触发 reauth，也返回合法 cookies 防止迭代失败。
    auth_bot.login.return_value = [
        {"name": "sessionid", "value": "abc", "domain": ".douyin.com"}
    ]

    downloader = MagicMock()
    # aaa → True（实际下载）；ccc → False（已存在，跳过）。
    # bbb 永远不会到达 Downloader（fetch 已失败 + 浏览器兜底也失败）。
    downloader.download.side_effect = [True, False]

    with patch(
        "douyin_dl.pipeline.parse_input", side_effect=_parse_side_effect
    ), patch(
        "douyin_dl.pipeline.fetch", side_effect=_fetch_side_effect
    ), patch(
        "douyin_dl.pipeline.time.sleep"
    ):
        pipe = DownloadPipeline(
            config=config,
            cookie_store=cookie_store,
            auth_bot=auth_bot,
            downloader=downloader,
            browser_fallback_fn=_browser_fallback_fn,
        )
        stats = pipe.run(URLS)

    # aaa: fetch 成功 + download=True → success
    # bbb: fetch 抛 FetcherError → browser_fallback 两种 kind 均失败 → failed
    # ccc: fetch 成功 + download=False → skipped
    assert stats.success == 1
    assert stats.failed == 1
    assert stats.skipped == 1

    # errors.log 存在且包含 bbb 的 URL。
    errors_log = tmp_path / "errors.log"
    assert errors_log.exists()
    content = errors_log.read_text(encoding="utf-8")
    assert "https://v.douyin.com/bbb/" in content

    # auth_bot 不应被调用（cookies 非空 + 未过期 + reauth=False）。
    auth_bot.login.assert_not_called()

    # 汇总信息应打印到 stdout。
    captured = capsys.readouterr()
    assert "完成：成功" in captured.out
