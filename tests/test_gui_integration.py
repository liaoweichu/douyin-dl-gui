"""DouyinDownloaderApp 集成测试：构造主窗口但不 mainloop。"""
from __future__ import annotations

import queue
import threading
from unittest.mock import MagicMock, patch

import tkinter as tk
import pytest

from douyin_dl.gui.app import DouyinDownloaderApp
from douyin_dl.progress import PipelineStats, ProgressEvent


@pytest.fixture
def app():
    app = DouyinDownloaderApp()
    app.withdraw()
    yield app
    app.destroy()


def test_app_initial_state(app):
    assert app.input_panel.get_urls() == []
    assert app.task_table.count() == 0
    assert str(app.start_button["state"]) == "normal"
    assert str(app.cancel_button["state"]) == "disabled"


def test_app_on_start_click_starts_worker(app):
    app.input_panel.insert_text("https://v.douyin.com/abc/\n")
    with patch("douyin_dl.gui.app.WorkerThread") as mock_worker_cls:
        mock_worker = MagicMock()
        mock_worker.is_alive.return_value = True
        mock_worker_cls.return_value = mock_worker
        app.on_start_click()
        mock_worker_cls.assert_called_once()
        mock_worker.start.assert_called_once()
        assert str(app.start_button["state"]) == "disabled"
        assert str(app.cancel_button["state"]) == "normal"


def test_app_drains_queue_updates_table(app):
    url = "https://v.douyin.com/abc/"
    app.task_table.add(url)
    app._event_queue.put(ProgressEvent(type="item_finished", url=url, status="success"))
    app._drain_queue()
    assert app.task_table.get_status(url) == "✓ 成功"


def test_app_drains_queue_updates_progress(app):
    url = "https://v.douyin.com/abc/"
    app.task_table.add(url)
    app._event_queue.put(
        ProgressEvent(
            type="download_progress", url=url, downloaded=300, content_length=600
        )
    )
    app._drain_queue()
    assert app.task_table.get_progress_text(url) == "50%"


def test_app_batch_finished_reenables_start(app):
    app.input_panel.insert_text("https://v.douyin.com/abc/\n")
    with patch("douyin_dl.gui.app.WorkerThread") as mock_worker_cls:
        mock_worker = MagicMock()
        mock_worker.is_alive.return_value = False
        mock_worker_cls.return_value = mock_worker
        app.on_start_click()
    stats = PipelineStats(success=1, failed=0, skipped=0)
    app._event_queue.put(ProgressEvent(type="batch_finished", stats=stats))
    app._drain_queue()
    assert str(app.start_button["state"]) == "normal"
    assert str(app.cancel_button["state"]) == "disabled"


def test_app_cancel_button_sets_event(app):
    app.input_panel.insert_text("https://v.douyin.com/abc/\n")
    with patch("douyin_dl.gui.app.WorkerThread") as mock_worker_cls:
        mock_worker = MagicMock()
        mock_worker.is_alive.return_value = True
        mock_worker_cls.return_value = mock_worker
        app.on_start_click()
    app.on_cancel_click()
    assert app._cancel_event.is_set()


def test_app_auth_required_triggers_callback(app):
    called = []

    def cb():
        called.append(True)

    app._event_queue.put(ProgressEvent(type="auth_required", callback=cb))
    with patch("douyin_dl.gui.app.AuthBot") as mock_auth_cls:
        mock_auth_cls.return_value.login.return_value = [{"name": "x", "value": "y"}]
        app._drain_queue()
    assert called == [True]


def test_e2e_three_links_two_success_one_fail(app):
    """端到端：3 条链接，2 成功 1 失败，验证表格与状态栏。"""
    urls = [
        "https://v.douyin.com/abc/",
        "https://v.douyin.com/def/",
        "https://v.douyin.com/ghi/",
    ]
    for u in urls:
        app.task_table.add(u)

    # 模拟 worker 投递事件序列
    for i, u in enumerate(urls):
        app._event_queue.put(ProgressEvent(
            type="item_started", url=u, index=i, total=3
        ))
        app._event_queue.put(ProgressEvent(type="stage", url=u, stage="parse"))
        app._event_queue.put(ProgressEvent(type="stage", url=u, stage="fetch"))
        app._event_queue.put(ProgressEvent(type="stage", url=u, stage="download"))

    # 1, 3 成功，2 失败
    app._event_queue.put(ProgressEvent(
        type="item_finished", url=urls[0], status="success"
    ))
    app._event_queue.put(ProgressEvent(
        type="item_finished", url=urls[1], status="failed", reason="链接已过期"
    ))
    app._event_queue.put(ProgressEvent(
        type="item_finished", url=urls[2], status="success"
    ))

    from douyin_dl.progress import PipelineStats
    stats = PipelineStats(success=2, failed=1, skipped=0)
    app._event_queue.put(ProgressEvent(type="batch_finished", stats=stats))

    app._drain_queue()

    # 验证表格状态
    assert app.task_table.get_status(urls[0]) == "✓ 成功"
    assert app.task_table.get_status(urls[1]) == "✗ 失败"
    assert app.task_table.get_reason(urls[1]) == "链接已过期"
    assert app.task_table.get_status(urls[2]) == "✓ 成功"

    # 验证按钮恢复
    assert str(app.start_button["state"]) == "normal"
    assert str(app.cancel_button["state"]) == "disabled"


def test_e2e_progress_updates_through_queue(app):
    """端到端：download_progress 事件正确推进进度列。"""
    url = "https://v.douyin.com/abc/"
    app.task_table.add(url)
    for d, t in [(0, 1000), (250, 1000), (500, 1000), (1000, 1000)]:
        app._event_queue.put(ProgressEvent(
            type="download_progress", url=url, downloaded=d, content_length=t
        ))
    app._drain_queue()
    assert app.task_table.get_progress_text(url) == "100%"
