"""ProgressEvent 与 Pipeline 回调支持的测试。"""
from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import douyin_dl.downloader as downloader_module
from douyin_dl.downloader import Downloader
from douyin_dl.models import Config, VideoMeta
from douyin_dl.pipeline import DownloadPipeline
from douyin_dl.progress import ProgressEvent


def test_progress_event_defaults():
    """ProgressEvent 只传 type 时其余字段使用默认值。"""
    e = ProgressEvent(type="item_finished")
    assert e.type == "item_finished"
    assert e.url == ""
    assert e.index == 0
    assert e.total == 0
    assert e.stage == ""
    assert e.status == ""
    assert e.reason == ""
    assert e.downloaded == 0
    assert e.content_length == 0
    assert e.stats is None
    assert e.message == ""
    assert e.callback is None


def test_progress_event_full_fields():
    """ProgressEvent 可指定所有字段。"""
    def cb():
        pass

    e = ProgressEvent(
        type="auth_required",
        url="https://v.douyin.com/abc/",
        index=2,
        total=5,
        stage="download",
        status="success",
        reason="",
        downloaded=1024,
        content_length=4096,
        stats=None,
        message="hello",
        callback=cb,
    )
    assert e.type == "auth_required"
    assert e.url == "https://v.douyin.com/abc/"
    assert e.index == 2
    assert e.total == 5
    assert e.stage == "download"
    assert e.status == "success"
    assert e.downloaded == 1024
    assert e.content_length == 4096
    assert e.message == "hello"
    assert e.callback is cb


class _FakeStreamResponse:
    """模拟 httpx 流式响应，按固定 chunk_size 切分 body。"""

    def __init__(self, body: bytes, status_code: int = 200) -> None:
        self._body = body
        self.status_code = status_code
        self.headers = {"Content-Length": str(len(body))}

    def iter_bytes(self, chunk_size: int = 8192):
        for i in range(0, len(self._body), chunk_size):
            yield self._body[i : i + chunk_size]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeClient:
    """模拟 httpx.Client，stream() 返回 _FakeStreamResponse 上下文管理器。"""

    def __init__(self, body: bytes, status_code: int = 200) -> None:
        self._body = body
        self._status_code = status_code

    def stream(self, method, url, headers=None, follow_redirects=False):
        return _FakeStreamResponse(self._body, self._status_code)


def test_downloader_with_progress_callback(tmp_path):
    """progress_callback 模式：禁用 tqdm，按 chunk 调用回调。"""
    chunk_size = 8192
    body = b"\x00" * (chunk_size * 3)
    total = len(body)

    save_path = tmp_path / "video.mp4"
    downloader = Downloader(client=_FakeClient(body))

    calls = []

    def callback(downloaded: int, total_bytes: int) -> None:
        calls.append((downloaded, total_bytes))

    result = downloader.download(
        "https://example.com/video.mp4",
        save_path,
        progress_callback=callback,
    )

    assert result is True
    # 8192*3 字节按 8192 chunk 切分恰好 3 个 chunk，回调至少 3 次
    assert len(calls) >= 3
    # 每次回调 total_bytes 都是完整文件大小
    assert all(t == total for _, t in calls)
    # 最后一次回调 downloaded == total
    assert calls[-1] == (total, total)
    # 文件内容正确
    assert save_path.read_bytes() == body


def test_downloader_without_progress_callback_uses_tqdm(tmp_path, monkeypatch):
    """不传 progress_callback 时维持 tqdm 行为：tqdm 被实例化且 pbar.update 被调用。"""
    chunk_size = 8192
    body = b"\x00" * (chunk_size * 3)

    class _FakePbar:
        instances = []

        def __init__(self, *args, **kwargs) -> None:
            self.updates = []
            self.closed = False
            _FakePbar.instances.append(self)

        def update(self, n: int) -> None:
            self.updates.append(n)

        def close(self) -> None:
            self.closed = True

    _FakePbar.instances.clear()
    monkeypatch.setattr(downloader_module, "tqdm", _FakePbar)

    save_path = tmp_path / "video.mp4"
    downloader = Downloader(client=_FakeClient(body))

    result = downloader.download("https://example.com/video.mp4", save_path)

    assert result is True
    # tqdm 被实例化一次
    assert len(_FakePbar.instances) == 1
    pbar = _FakePbar.instances[0]
    # pbar.update 被调用至少 3 次（3 个 chunk）
    assert len(pbar.updates) >= 3
    assert sum(pbar.updates) == len(body)
    # pbar.close 被调用
    assert pbar.closed is True
    # 文件内容正确
    assert save_path.read_bytes() == body


# --- Pipeline 回调与取消支持 -------------------------------------------------


def _make_config(tmp_path: Path) -> Config:
    return Config(
        output_dir=tmp_path / "out",
        cookie_path=tmp_path / "cookies.json",
        reauth=False,
        sleep_range=(0.0, 0.0),
    )


def _make_cookie_store():
    cs = MagicMock()
    cs.is_expired.return_value = False
    cs.get_cookies.return_value = [{"name": "sid", "value": "v", "domain": ".douyin.com"}]
    return cs


def _make_video_meta(aweme_id="aid1", video_url="https://x/v.mp4"):
    return VideoMeta(aweme_id=aweme_id, video_url=video_url, type="normal")


def _make_pipeline_with_callback(
    config, events, *, fetch_fn=None, downloader=None, cancel_event=None,
    download_progress_callback=None,
):
    """构造一个接收事件的 pipeline。"""
    def cb(ev):
        events.append(ev)
    return DownloadPipeline(
        config=config,
        cookie_store=_make_cookie_store(),
        auth_bot=MagicMock(),
        downloader=downloader or MagicMock(),
        fetch_fn=fetch_fn,
        progress_callback=cb,
        cancel_event=cancel_event,
        download_progress_callback=download_progress_callback,
    )


def test_pipeline_emits_batch_started_first(tmp_path):
    """第一个事件是 batch_started，total=1。"""
    config = _make_config(tmp_path)
    events = []
    fetch_fn = MagicMock(return_value=_make_video_meta())
    downloader = MagicMock()
    downloader.download.return_value = True

    pipe = _make_pipeline_with_callback(config, events, fetch_fn=fetch_fn, downloader=downloader)

    with patch("douyin_dl.pipeline.parse_input", return_value=("id1", None)):
        pipe.run(["u1"])

    assert events, "应当至少投递一个事件"
    assert events[0].type == "batch_started"
    assert events[0].total == 1


def test_pipeline_emits_item_started_per_url(tmp_path):
    """3 个 URL 触发 3 个 item_started，index/total 正确。"""
    config = _make_config(tmp_path)
    events = []
    fetch_fn = MagicMock(return_value=_make_video_meta())
    downloader = MagicMock()
    downloader.download.return_value = True

    pipe = _make_pipeline_with_callback(config, events, fetch_fn=fetch_fn, downloader=downloader)

    with patch(
        "douyin_dl.pipeline.parse_input",
        side_effect=[("id1", None), ("id2", None), ("id3", None)],
    ):
        pipe.run(["u1", "u2", "u3"])

    item_started = [e for e in events if e.type == "item_started"]
    assert len(item_started) == 3
    for i, ev in enumerate(item_started):
        assert ev.url == f"u{i + 1}"
        assert ev.index == i
        assert ev.total == 3


def test_pipeline_emits_stage_events_in_order(tmp_path):
    """stage 顺序 parse → fetch → download。"""
    config = _make_config(tmp_path)
    events = []
    fetch_fn = MagicMock(return_value=_make_video_meta())
    downloader = MagicMock()
    downloader.download.return_value = True

    pipe = _make_pipeline_with_callback(config, events, fetch_fn=fetch_fn, downloader=downloader)

    with patch("douyin_dl.pipeline.parse_input", return_value=("id1", None)):
        pipe.run(["u1"])

    stages = [e.stage for e in events if e.type == "stage"]
    assert stages == ["parse", "fetch", "download"]


def test_pipeline_emits_item_finished_success(tmp_path):
    """成功时 item_finished(status="success")。"""
    config = _make_config(tmp_path)
    events = []
    fetch_fn = MagicMock(return_value=_make_video_meta())
    downloader = MagicMock()
    downloader.download.return_value = True

    pipe = _make_pipeline_with_callback(config, events, fetch_fn=fetch_fn, downloader=downloader)

    with patch("douyin_dl.pipeline.parse_input", return_value=("id1", None)):
        pipe.run(["u1"])

    finished = [e for e in events if e.type == "item_finished"]
    assert finished, "应当至少有一个 item_finished 事件"
    success_events = [e for e in finished if e.status == "success"]
    assert success_events, "应当有一个 status=success 的事件"
    assert success_events[-1].url == "u1"


def test_pipeline_emits_item_finished_failed_with_reason(tmp_path):
    """fetch 失败 + 兜底失败时 item_finished(status="failed", reason 含 boom 或 兜底)。"""
    from douyin_dl.browser_fallback import BrowserFallbackError
    from douyin_dl.fetcher import FetcherError

    config = _make_config(tmp_path)
    events = []
    # fetch_fn 抛 FetcherError 触发兜底路径
    fetch_fn = MagicMock(side_effect=FetcherError("boom"))
    # fallback_fn 在 video/note 两种 kind 都失败
    fallback_fn = MagicMock(side_effect=BrowserFallbackError("nope"))
    downloader = MagicMock()

    pipe = DownloadPipeline(
        config=config,
        cookie_store=_make_cookie_store(),
        auth_bot=MagicMock(),
        downloader=downloader,
        fetch_fn=fetch_fn,
        browser_fallback_fn=fallback_fn,
        progress_callback=lambda ev: events.append(ev),
    )

    with patch("douyin_dl.pipeline.parse_input", return_value=("id1", None)):
        pipe.run(["u1"])

    finished = [e for e in events if e.type == "item_finished"]
    assert finished, "应当至少有一个 item_finished 事件"
    failed_events = [e for e in finished if e.status == "failed"]
    assert failed_events, "应当有 status=failed 的事件"
    reason = failed_events[-1].reason
    assert "boom" in reason or "兜底" in reason, f"reason 应含 boom 或 兜底，实际：{reason}"


def test_pipeline_emits_batch_finished_with_stats(tmp_path):
    """batch_finished.stats.success==2。"""
    config = _make_config(tmp_path)
    events = []
    fetch_fn = MagicMock(return_value=_make_video_meta())
    downloader = MagicMock()
    downloader.download.return_value = True

    pipe = _make_pipeline_with_callback(config, events, fetch_fn=fetch_fn, downloader=downloader)

    with patch(
        "douyin_dl.pipeline.parse_input",
        side_effect=[("id1", None), ("id2", None)],
    ):
        pipe.run(["u1", "u2"])

    batch_finished = [e for e in events if e.type == "batch_finished"]
    assert batch_finished, "应当有 batch_finished 事件"
    assert batch_finished[-1].stats is not None
    assert batch_finished[-1].stats.success == 2


def test_pipeline_cancel_event_stops_after_current(tmp_path):
    """cancel 在 u2 时 set，验证只处理 u1, u2，u3 跳过，stats.skipped==1。"""
    config = _make_config(tmp_path)
    events = []
    cancel_event = threading.Event()

    metas = {
        "u1": _make_video_meta(aweme_id="u1"),
        "u2": _make_video_meta(aweme_id="u2"),
        "u3": _make_video_meta(aweme_id="u3"),
    }

    def fetch_side_effect(aweme_id, client):
        if aweme_id == "u2":
            cancel_event.set()
        return metas[aweme_id]

    fetch_fn = MagicMock(side_effect=fetch_side_effect)
    downloader = MagicMock()
    downloader.download.return_value = True

    pipe = _make_pipeline_with_callback(
        config, events, fetch_fn=fetch_fn, downloader=downloader,
        cancel_event=cancel_event,
    )

    with patch(
        "douyin_dl.pipeline.parse_input",
        side_effect=[("u1", None), ("u2", None), ("u3", None)],
    ):
        stats = pipe.run(["u1", "u2", "u3"])

    assert stats.success == 2
    assert stats.skipped == 1
    assert stats.failed == 0
    # 验证只处理了 u1, u2
    item_started = [e for e in events if e.type == "item_started"]
    assert len(item_started) == 2
    assert item_started[0].url == "u1"
    assert item_started[1].url == "u2"


def test_pipeline_progress_callback_none_keeps_print(tmp_path, capsys):
    """不传 progress_callback 时仍 print（用 capsys 验证包含 "完成"）。"""
    config = _make_config(tmp_path)
    fetch_fn = MagicMock(return_value=_make_video_meta())
    downloader = MagicMock()
    downloader.download.return_value = True

    pipe = DownloadPipeline(
        config=config,
        cookie_store=_make_cookie_store(),
        auth_bot=MagicMock(),
        downloader=downloader,
        fetch_fn=fetch_fn,
    )

    with patch("douyin_dl.pipeline.parse_input", return_value=("id1", None)):
        pipe.run(["u1"])

    captured = capsys.readouterr()
    assert "完成" in captured.out


def test_pipeline_download_progress_callback_forwarded(tmp_path):
    """download_progress_callback 不为 None 时 download 调用 kwargs 含 progress_callback。"""
    config = _make_config(tmp_path)
    events = []
    fetch_fn = MagicMock(return_value=_make_video_meta())
    downloader = MagicMock()
    downloader.download.return_value = True

    def dpc(url, d, t):
        events.append(("dpc", url, d, t))

    pipe = DownloadPipeline(
        config=config,
        cookie_store=_make_cookie_store(),
        auth_bot=MagicMock(),
        downloader=downloader,
        fetch_fn=fetch_fn,
        download_progress_callback=dpc,
    )

    with patch("douyin_dl.pipeline.parse_input", return_value=("id1", None)):
        pipe.run(["u1"])

    assert downloader.download.called
    call_kwargs = downloader.download.call_args.kwargs
    assert "progress_callback" in call_kwargs
    assert callable(call_kwargs["progress_callback"])
