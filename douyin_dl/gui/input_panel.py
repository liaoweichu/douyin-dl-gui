"""链接输入区组件：多行文本框 + 剪贴板粘贴 / 清空按钮。"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk


def _extract_urls(text: str) -> list[str]:
    """从多行文本中提取 URL。

    - 按 ``splitlines()`` 拆行
    - 跳过空行和以 ``#`` 开头的注释行
    - 只保留以 ``http`` 开头的行（取首个连续非空白 token）
    - 用 ``seen`` 去重，保持首次出现顺序
    """
    urls: list[str] = []
    seen: set[str] = set()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue
        parts = stripped.split()
        token = parts[0] if parts else ""
        if token.startswith("http") and token not in seen:
            seen.add(token)
            urls.append(token)
    return urls


class InputPanel(ttk.Frame):
    """链接输入区：顶部标题 + 左侧多行文本框 + 右侧按钮组。"""

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent)

        title = ttk.Label(self, text="── 链接输入 ──")
        title.pack(anchor="w", padx=4, pady=(2, 4))

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)

        self._text = tk.Text(body, height=6, wrap="word")
        self._text.pack(side="left", fill="both", expand=True)

        btn_box = ttk.Frame(body)
        btn_box.pack(side="right", fill="y", padx=(4, 0))

        self._paste_btn = ttk.Button(
            btn_box, text="从剪贴板粘贴", command=self.paste_from_clipboard
        )
        self._paste_btn.pack(anchor="w", pady=2)

        self._clear_btn = ttk.Button(btn_box, text="清空", command=self.clear)
        self._clear_btn.pack(anchor="w", pady=2)

    def insert_text(self, text: str) -> None:
        """追加文本到末尾。"""
        self._text.insert("end", text)

    def get_text(self) -> str:
        """取文本框全部内容（不含末尾换行）。"""
        return self._text.get("1.0", "end-1c")

    def clear(self) -> None:
        """清空文本框。"""
        self._text.delete("1.0", "end")

    def get_urls(self) -> list[str]:
        """从文本框提取去重后的 URL 列表。"""
        return _extract_urls(self.get_text())

    def paste_from_clipboard(self) -> None:
        """从系统剪贴板读取并追加到文本框末尾（加换行）。

        剪贴板不可用（TclError）时静默返回。
        """
        try:
            content = self.clipboard_get()
        except tk.TclError:
            return
        if content:
            self._text.insert("end", content + "\n")
