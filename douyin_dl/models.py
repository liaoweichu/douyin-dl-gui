"""数据模型与配置定义。"""

from __future__ import annotations

import dataclasses
import pathlib
from dataclasses import field


@dataclasses.dataclass
class VideoMeta:
    """抖音视频元数据。"""

    aweme_id: str
    type: str = field(default="normal")
    title: str = field(default="")
    author: str = field(default="")
    video_url: str = field(default="")
    cover_url: str = field(default="")
    is_story: bool = field(default=False)
    is_24_story: bool = field(default=False)

    @property
    def is_story_video(self) -> bool:
        """是否为 Story 视频（日常或 24 小时 Story）。"""
        return self.is_story or self.is_24_story


@dataclasses.dataclass
class Config:
    """下载器运行配置。"""

    output_dir: pathlib.Path = field(default=pathlib.Path("./downloads"))
    cookie_path: pathlib.Path = field(
        default=pathlib.Path.home() / ".douyin_dl" / "cookies.json"
    )
    quality: str = field(default="default")
    reauth: bool = field(default=False)
    sleep_range: tuple[float, float] = field(default=(1.0, 2.0))

    def __post_init__(self) -> None:
        # CookieStore 负责创建 cookie_path.parent 目录，此处不做任何文件系统操作。
        _ = self.cookie_path.parent
