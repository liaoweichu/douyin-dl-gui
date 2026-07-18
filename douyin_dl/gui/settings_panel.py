"""设置面板组件：输出目录、画质、强制重新登录等运行配置。"""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

from douyin_dl.models import Config


class SettingsPanel(ttk.Frame):
    """设置区：输出目录 / 画质 / 强制重新登录。"""

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent)

        title = ttk.Label(self, text="── 设置 ──")
        title.grid(row=0, column=0, columnspan=3, sticky="w", padx=4, pady=(2, 4))

        # 第 0 行：输出目录
        out_label = ttk.Label(self, text="输出目录:")
        out_label.grid(row=1, column=0, sticky="w", padx=4, pady=2)

        self._output_dir = tk.StringVar()
        self._out_entry = ttk.Entry(self, textvariable=self._output_dir, width=40)
        self._out_entry.grid(row=1, column=1, sticky="w", padx=4, pady=2)

        self._browse_btn = ttk.Button(self, text="浏览...", command=self._browse)
        self._browse_btn.grid(row=1, column=2, padx=4, pady=2)

        # 第 1 行：画质
        quality_label = ttk.Label(self, text="画质:")
        quality_label.grid(row=2, column=0, sticky="w", padx=4, pady=2)

        self._quality = tk.StringVar()
        self._quality_combo = ttk.Combobox(
            self,
            textvariable=self._quality,
            values=["default", "720p", "1080p", "原画"],
            state="readonly",
            width=10,
        )
        self._quality_combo.current(0)
        self._quality_combo.grid(row=2, column=1, sticky="w", padx=4, pady=2)

        # 第 2 行：强制重新登录
        self._reauth = tk.BooleanVar()
        self._reauth_check = ttk.Checkbutton(
            self, text="强制重新登录", variable=self._reauth
        )
        self._reauth_check.grid(row=3, column=0, columnspan=3, sticky="w", padx=4, pady=2)

    def _browse(self) -> None:
        """打开目录选择对话框，非空时设置输出目录 StringVar。"""
        initial = self._output_dir.get() or None
        path = filedialog.askdirectory(initialdir=initial)
        if path:
            self._output_dir.set(path)

    def set_output_dir(self, path: str) -> None:
        """设置输出目录 StringVar。"""
        self._output_dir.set(path)

    def set_quality(self, quality: str) -> None:
        """设置画质 StringVar。"""
        self._quality.set(quality)

    def set_reauth(self, reauth: bool) -> None:
        """设置强制重新登录 BooleanVar。"""
        self._reauth.set(reauth)

    def get_config(self) -> Config:
        """根据当前面板值构造 Config。"""
        return Config(
            output_dir=Path(self._output_dir.get() or "./downloads"),
            quality=self._quality.get() or "default",
            reauth=bool(self._reauth.get()),
        )
