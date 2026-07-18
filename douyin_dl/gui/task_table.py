"""任务表格组件：展示每条 URL 的状态、进度与失败原因。"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class TaskTable(ttk.Frame):
    """ttk.Treeview 包装，列：URL / 状态 / 进度 / 失败原因。"""

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent)
        self._row_ids: dict[str, str] = {}  # url -> treeview item id

        # 滚动条
        scrollbar = ttk.Scrollbar(self, orient="vertical")
        scrollbar.pack(side="right", fill="y")

        self._tree = ttk.Treeview(
            self,
            columns=("url", "status", "progress", "reason"),
            show="headings",
            yscrollcommand=scrollbar.set,
        )
        self._tree.heading("url", text="URL")
        self._tree.heading("status", text="状态")
        self._tree.heading("progress", text="进度")
        self._tree.heading("reason", text="失败原因")
        self._tree.column("url", width=300, anchor="w")
        self._tree.column("status", width=80, anchor="center")
        self._tree.column("progress", width=80, anchor="center")
        self._tree.column("reason", width=120, anchor="w")
        self._tree.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self._tree.yview)

    def add(self, url: str) -> None:
        """添加一条 URL 行，初始状态「等待」。已存在则跳过。"""
        if url in self._row_ids:
            return  # 去重
        item_id = self._tree.insert("", "end", values=(url, "等待", "", ""))
        self._row_ids[url] = item_id

    def set_status(self, url: str, status: str) -> None:
        """更新 URL 行的状态列。"""
        item_id = self._row_ids.get(url)
        if item_id is None:
            return
        values = list(self._tree.item(item_id, "values"))
        values[1] = status
        self._tree.item(item_id, values=values)

    def set_progress(self, url: str, downloaded: int, total: int) -> None:
        """更新进度列：downloaded/total 百分比；total<=0 时设为空字符串。"""
        item_id = self._row_ids.get(url)
        if item_id is None:
            return
        if total <= 0:
            text = ""
        else:
            pct = int(downloaded * 100 / total)
            text = f"{pct}%"
        values = list(self._tree.item(item_id, "values"))
        values[2] = text
        self._tree.item(item_id, values=values)

    def set_reason(self, url: str, reason: str) -> None:
        """更新失败原因列。"""
        item_id = self._row_ids.get(url)
        if item_id is None:
            return
        values = list(self._tree.item(item_id, "values"))
        values[3] = reason
        self._tree.item(item_id, values=values)

    def get_status(self, url: str) -> str:
        """读取状态列。"""
        return self._get_value(url, 1)

    def get_progress_text(self, url: str) -> str:
        """读取进度列。"""
        return self._get_value(url, 2)

    def get_reason(self, url: str) -> str:
        """读取失败原因列。"""
        return self._get_value(url, 3)

    def _get_value(self, url: str, index: int) -> str:
        """统一读取指定列的值。"""
        item_id = self._row_ids.get(url)
        if item_id is None:
            return ""
        values = self._tree.item(item_id, "values")
        return values[index] if index < len(values) else ""

    def count(self) -> int:
        """返回当前行数。"""
        return len(self._row_ids)

    def clear(self) -> None:
        """清空所有行。"""
        for item_id in list(self._row_ids.values()):
            self._tree.delete(item_id)
        self._row_ids.clear()
