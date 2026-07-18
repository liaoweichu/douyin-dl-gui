"""状态栏组件：显示 pipeline 总进度与统计。"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from douyin_dl.progress import PipelineStats


class StatusBar(ttk.Frame):
    """底部状态栏：单行文本显示总进度 / 成功 / 失败 / 跳过。"""

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent)

        self._var = tk.StringVar(value="就绪")
        self._label = ttk.Label(self, textvariable=self._var, anchor="w")
        self._label.pack(fill="x")

    def update(self, stats: PipelineStats, total: int = 0) -> None:
        """根据 PipelineStats 更新状态文本。total<=0 时显示 ``?``。"""
        done = stats.success + stats.failed + stats.skipped
        denom = total if total > 0 else "?"
        self._var.set(
            f"总进度 {done}/{denom}  成功 {stats.success}  "
            f"失败 {stats.failed}  跳过 {stats.skipped}"
        )

    def set_message(self, text: str) -> None:
        """直接设置状态文本。"""
        self._var.set(text)

    def get_text(self) -> str:
        """读取当前状态文本。"""
        return self._var.get()
