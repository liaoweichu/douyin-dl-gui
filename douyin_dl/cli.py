"""douyin_dl 命令行入口：解析参数、收集链接、调度下载管线。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from douyin_dl import __version__
from douyin_dl.auth_bot import AuthBot
from douyin_dl.cookie_store import CookieStore
from douyin_dl.models import Config
from douyin_dl.pipeline import DownloadPipeline


class LinkCollector:
    """合并多个来源的链接：CLI 位置参数、文件、stdin。"""

    @staticmethod
    def collect(
        urls: list[str],
        file_path: str | None,
        stdin_text: str | None,
    ) -> list[str]:
        """合并三个来源的链接。

        - 逐行去除首尾空白。
        - 跳过空行与以 ``#`` 开头的注释行。
        - 按首次出现顺序去重。
        """
        raw: list[str] = list(urls) if urls else []

        if file_path is not None:
            with Path(file_path).open("r", encoding="utf-8") as f:
                raw.extend(f.read().splitlines())

        if stdin_text is not None:
            raw.extend(stdin_text.splitlines())

        seen: set[str] = set()
        result: list[str] = []
        for line in raw:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("#"):
                continue
            if stripped in seen:
                continue
            seen.add(stripped)
            result.append(stripped)
        return result


def parse_args(
    argv: list[str] | None = None,
) -> tuple[argparse.Namespace, Config]:
    """解析命令行参数并构造 Config。返回 ``(args, config)``。"""
    parser = argparse.ArgumentParser(
        prog="python -m douyin_dl",
        description="抖音批量视频下载器",
    )
    parser.add_argument(
        "urls",
        nargs="*",
        default=[],
        help="一个或多个抖音视频链接",
    )
    parser.add_argument(
        "-f",
        "--file",
        type=str,
        default=None,
        help="包含链接的文件路径（每行一条）",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default="./downloads",
        help="输出目录（默认 ./downloads）",
    )
    parser.add_argument(
        "--reauth",
        action="store_true",
        help="强制重新登录",
    )
    parser.add_argument(
        "--quality",
        type=str,
        default="default",
        choices=["default", "720p", "1080p", "原画"],
        help="视频画质偏好",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=__version__,
    )

    args = parser.parse_args(argv)

    config = Config(
        output_dir=Path(args.output),
        cookie_path=Path.home() / ".douyin_dl" / "cookies.json",
        quality=args.quality,
        reauth=args.reauth,
    )
    return args, config


def main(argv: list[str] | None = None) -> int:
    """CLI 主入口：解析参数、收集链接、运行下载管线。"""
    args, config = parse_args(argv)

    stdin_text: str | None = None
    if not sys.stdin.isatty():
        stdin_text = sys.stdin.read()

    urls = LinkCollector.collect(args.urls, args.file, stdin_text)

    if not urls:
        print(
            "用法: python -m douyin_dl <url1> <url2> ... | "
            "-f links.txt | cat links.txt | python -m douyin_dl",
            file=sys.stderr,
        )
        return 2

    print(f"共 {len(urls)} 条链接待下载")

    cookie_store = CookieStore(config.cookie_path)
    auth_bot = AuthBot()
    pipeline = DownloadPipeline(
        config=config,
        cookie_store=cookie_store,
        auth_bot=auth_bot,
    )
    pipeline.run(urls)
    return 0
