"""主窗口：组装 GUI 组件并处理跨线程事件分发。"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Optional

from douyin_dl.auth_bot import AuthBot
from douyin_dl.gui.input_panel import InputPanel
from douyin_dl.gui.settings_panel import SettingsPanel
from douyin_dl.gui.status_bar import StatusBar
from douyin_dl.gui.task_table import TaskTable
from douyin_dl.gui.worker import WorkerThread
from douyin_dl.progress import (
    EVENT_AUTH_REQUIRED,
    EVENT_BATCH_FINISHED,
    EVENT_DOWNLOAD_PROGRESS,
    EVENT_ITEM_FINISHED,
    EVENT_ITEM_STARTED,
    EVENT_STAGE,
    ProgressEvent,
)


_STAGE_LABEL = {
    "parse": "解析中",
    "fetch": "解析中",
    "fallback": "浏览器兜底",
    "download": "下载中",
}

_STATUS_LABEL = {
    "success": "✓ 成功",
    "failed": "✗ 失败",
    "skipped": "⏭ 跳过",
}


class DouyinDownloaderApp(tk.Tk):
    """主窗口：组装输入/设置/任务表/状态栏，并处理事件分发。"""

    def __init__(self) -> None:
        super().__init__()
        self.title("抖音下载器")
        self.geometry("760x560")

        self._event_queue: "queue.Queue[ProgressEvent]" = queue.Queue()
        self._cancel_event = threading.Event()
        self._worker: Optional[WorkerThread] = None

        # 组件自上而下 pack
        self.input_panel = InputPanel(self)
        self.input_panel.pack(fill="x")

        self.settings_panel = SettingsPanel(self)
        self.settings_panel.pack(fill="x")

        ttk.Label(self, text="── 任务列表 ──").pack(anchor="w")

        self.task_table = TaskTable(self)
        self.task_table.pack(fill="both", expand=True)

        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill="x")
        self.start_button = ttk.Button(
            btn_frame, text="开始下载", command=self.on_start_click
        )
        self.start_button.pack(side="left", padx=4, pady=4)
        self.cancel_button = ttk.Button(
            btn_frame,
            text="取消",
            command=self.on_cancel_click,
            state="disabled",
        )
        self.cancel_button.pack(side="left", padx=4, pady=4)

        self.status_bar = StatusBar(self)
        self.status_bar.pack(fill="x", side="bottom")

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(50, self._drain_queue)

    def on_start_click(self) -> None:
        urls = self.input_panel.get_urls()
        if not urls:
            messagebox.showwarning("提示", "请先输入至少一条链接")
            return

        self.task_table.clear()
        for u in urls:
            self.task_table.add(u)

        self.start_button.config(state="disabled")
        self.cancel_button.config(state="normal")
        self._cancel_event.clear()
        self.status_bar.set_message(f"开始处理 {len(urls)} 条...")

        config = self.settings_panel.get_config()
        self._worker = WorkerThread(
            urls=urls,
            config=config,
            event_queue=self._event_queue,
            cancel_event=self._cancel_event,
        )
        self._worker.start()

    def on_cancel_click(self) -> None:
        self._cancel_event.set()
        self.status_bar.set_message("正在取消...")
        self.cancel_button.config(state="disabled")

    def _drain_queue(self) -> None:
        try:
            while True:
                event = self._event_queue.get_nowait()
                self._handle_event(event)
        except queue.Empty:
            pass
        self.after(50, self._drain_queue)

    def _handle_event(self, event: ProgressEvent) -> None:
        if event.type == EVENT_ITEM_STARTED:
            self.task_table.set_status(event.url, "等待")
        elif event.type == EVENT_STAGE:
            label = _STAGE_LABEL.get(event.stage, event.stage)
            self.task_table.set_status(event.url, label)
        elif event.type == EVENT_DOWNLOAD_PROGRESS:
            self.task_table.set_progress(
                event.url, event.downloaded, event.content_length
            )
        elif event.type == EVENT_ITEM_FINISHED:
            label = _STATUS_LABEL.get(event.status, event.status)
            self.task_table.set_status(event.url, label)
            if event.reason:
                self.task_table.set_reason(event.url, event.reason)
        elif event.type == EVENT_AUTH_REQUIRED:
            self._do_login(event)
        elif event.type == EVENT_BATCH_FINISHED:
            self._on_batch_finished(event)
        elif event.type == "log":
            self.status_bar.set_message(event.message)

    def _do_login(self, event: ProgressEvent) -> None:
        try:
            if event.callback is not None:
                event.callback()
            else:
                AuthBot().login()
        except Exception as e:
            messagebox.showerror("登录失败", str(e))

    def _on_batch_finished(self, event: ProgressEvent) -> None:
        stats = event.stats
        if stats is not None:
            total = stats.success + stats.failed + stats.skipped
            self.status_bar.update(stats, total=total)
        self.start_button.config(state="normal")
        self.cancel_button.config(state="disabled")
        self._worker = None

    def _on_close(self) -> None:
        if self._worker and self._worker.is_alive():
            if not messagebox.askokcancel("确认", "下载仍在进行，确定退出吗？"):
                return
            self._cancel_event.set()
            self._worker.join(timeout=10)
        self.destroy()
