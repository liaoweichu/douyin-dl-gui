"""CLI 入口（python -m douyin_dl 和 douyin-dl 命令共用）。"""

import sys

from douyin_dl.cli import main as cli_main


def main() -> int:
    return cli_main()


if __name__ == "__main__":
    sys.exit(main())
