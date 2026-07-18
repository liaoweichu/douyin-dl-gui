"""GUI 入口：python -m douyin_dl.gui"""
from __future__ import annotations

import sys


def main() -> int:
    """启动 Tkinter 主窗口。"""
    from douyin_dl.gui.app import DouyinDownloaderApp

    app = DouyinDownloaderApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
