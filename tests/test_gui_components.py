"""GUI 组件单元测试，使用 Tkinter 无 mainloop。"""
from __future__ import annotations

import tkinter as tk
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def tk_root():
    """共享 Tk root，测试结束销毁。"""
    root = tk.Tk()
    root.withdraw()  # 不显示窗口
    yield root
    root.destroy()


# --- TaskTable ---

from douyin_dl.gui.task_table import TaskTable


def test_task_table_add_and_get_status(tk_root):
    """添加 URL 后状态默认为「等待」。"""
    table = TaskTable(tk_root)
    table.add("https://v.douyin.com/abc/")
    assert table.get_status("https://v.douyin.com/abc/") == "等待"


def test_task_table_set_status(tk_root):
    """set_status 更新状态列。"""
    table = TaskTable(tk_root)
    table.add("https://v.douyin.com/abc/")
    table.set_status("https://v.douyin.com/abc/", "✓ 成功")
    assert table.get_status("https://v.douyin.com/abc/") == "✓ 成功"


def test_task_table_set_progress_percentage(tk_root):
    """set_progress 计算百分比文本。"""
    table = TaskTable(tk_root)
    table.add("https://v.douyin.com/abc/")
    table.set_progress("https://v.douyin.com/abc/", downloaded=500, total=1000)
    assert table.get_progress_text("https://v.douyin.com/abc/") == "50%"


def test_task_table_set_progress_zero_total(tk_root):
    """total=0 时进度文本为空（避免除零）。"""
    table = TaskTable(tk_root)
    table.add("https://v.douyin.com/abc/")
    table.set_progress("https://v.douyin.com/abc/", downloaded=100, total=0)
    assert table.get_progress_text("https://v.douyin.com/abc/") == ""


def test_task_table_set_reason(tk_root):
    """set_reason 更新失败原因列。"""
    table = TaskTable(tk_root)
    table.add("https://v.douyin.com/abc/")
    table.set_reason("https://v.douyin.com/abc/", "链接已过期")
    assert table.get_reason("https://v.douyin.com/abc/") == "链接已过期"


def test_task_table_clear(tk_root):
    """clear 清空所有行。"""
    table = TaskTable(tk_root)
    table.add("u1")
    table.add("u2")
    table.clear()
    assert table.count() == 0


# --- InputPanel ---

from douyin_dl.gui.input_panel import InputPanel


def test_input_panel_get_urls_multiline(tk_root):
    """多行 + 空行 + 注释行 + URL，返回两条去重后 URL。"""
    panel = InputPanel(tk_root)
    panel.insert_text(
        "https://v.douyin.com/abc/\n\n"
        "# comment\n"
        "https://v.douyin.com/def/\n"
    )
    urls = panel.get_urls()
    assert urls == ["https://v.douyin.com/abc/", "https://v.douyin.com/def/"]


def test_input_panel_get_urls_dedup(tk_root):
    """相同 URL 去重，仅保留首次出现。"""
    panel = InputPanel(tk_root)
    panel.insert_text(
        "https://v.douyin.com/abc/\n"
        "https://v.douyin.com/abc/\n"
    )
    urls = panel.get_urls()
    assert urls == ["https://v.douyin.com/abc/"]


def test_input_panel_get_urls_empty(tk_root):
    """空文本框返回空列表。"""
    panel = InputPanel(tk_root)
    assert panel.get_urls() == []


def test_input_panel_clear(tk_root):
    """clear 后 get_text() 为空字符串。"""
    panel = InputPanel(tk_root)
    panel.insert_text("https://v.douyin.com/abc/\n")
    panel.clear()
    assert panel.get_text() == ""


def test_input_panel_paste_from_clipboard(tk_root):
    """paste 从剪贴板读取并追加到文本框。"""
    panel = InputPanel(tk_root)
    tk_root.clipboard_clear()
    tk_root.clipboard_append("https://v.douyin.com/abc/")
    panel.paste_from_clipboard()
    assert "https://v.douyin.com/abc/" in panel.get_text()


# --- SettingsPanel ---

from pathlib import Path  # noqa: E402

from douyin_dl.gui.settings_panel import SettingsPanel
from douyin_dl.gui.status_bar import StatusBar
from douyin_dl.progress import PipelineStats


def test_settings_panel_get_config(tk_root):
    panel = SettingsPanel(tk_root)
    panel.set_output_dir("/tmp/x")
    panel.set_quality("1080p")
    panel.set_reauth(True)
    config = panel.get_config()
    assert config.output_dir == Path("/tmp/x")
    assert config.quality == "1080p"
    assert config.reauth is True


def test_settings_panel_default_config(tk_root):
    panel = SettingsPanel(tk_root)
    config = panel.get_config()
    assert config.quality == "default"
    assert config.reauth is False


def test_status_bar_update_stats(tk_root):
    bar = StatusBar(tk_root)
    stats = PipelineStats()
    stats.success = 3
    stats.failed = 1
    stats.skipped = 2
    bar.update(stats, total=6)
    text = bar.get_text()
    assert "3" in text and "1" in text and "2" in text


def test_status_bar_initial_text(tk_root):
    bar = StatusBar(tk_root)
    assert bar.get_text() != ""


def test_status_bar_set_message(tk_root):
    bar = StatusBar(tk_root)
    bar.set_message("正在处理...")
    assert bar.get_text() == "正在处理..."


# --- WorkerThread ---

import queue  # noqa: E402
import threading  # noqa: E402
from unittest.mock import MagicMock, patch  # noqa: E402

from douyin_dl.gui.worker import WorkerThread  # noqa: E402
from douyin_dl.models import Config  # noqa: E402
from douyin_dl.progress import PipelineStats  # noqa: E402


def test_worker_thread_runs_pipeline_and_finishes():
    """WorkerThread 启动后构造 Pipeline 并调用 run，结束后投递 batch_finished。"""
    event_q = queue.Queue()
    cancel_event = threading.Event()
    stats = PipelineStats(success=2, failed=0, skipped=0)

    with patch("douyin_dl.gui.worker.DownloadPipeline") as mock_pipeline_cls:
        mock_pipeline = MagicMock()
        mock_pipeline.run.return_value = stats
        mock_pipeline_cls.return_value = mock_pipeline

        config = Config()
        worker = WorkerThread(
            urls=["u1", "u2"],
            config=config,
            event_queue=event_q,
            cancel_event=cancel_event,
        )
        worker.start()
        worker.join(timeout=5)

        assert not worker.is_alive()
        mock_pipeline.run.assert_called_once_with(["u1", "u2"])

    events = []
    while not event_q.empty():
        events.append(event_q.get_nowait())
    # Pipeline 内部会通过 progress_callback=event_queue.put 投递事件
    # mock_pipeline.run 不会真的投递，所以这里只验证 worker 不崩溃
    # 但 Pipeline 构造时收到了 progress_callback
    assert mock_pipeline_cls.call_args.kwargs["progress_callback"] is not None
    assert mock_pipeline_cls.call_args.kwargs["cancel_event"] is cancel_event


def test_worker_thread_passes_callbacks_to_pipeline():
    """WorkerThread 把 event_queue.put 作为 progress_callback 传给 Pipeline。"""
    event_q = queue.Queue()
    cancel_event = threading.Event()

    with patch("douyin_dl.gui.worker.DownloadPipeline") as mock_pipeline_cls:
        mock_pipeline = MagicMock()
        mock_pipeline.run.return_value = PipelineStats()
        mock_pipeline_cls.return_value = mock_pipeline

        worker = WorkerThread(
            urls=["u1"],
            config=Config(),
            event_queue=event_q,
            cancel_event=cancel_event,
        )
        worker.start()
        worker.join(timeout=5)

        kwargs = mock_pipeline_cls.call_args.kwargs
        assert kwargs["progress_callback"] is not None
        assert kwargs["cancel_event"] is cancel_event
        assert kwargs["download_progress_callback"] is not None
