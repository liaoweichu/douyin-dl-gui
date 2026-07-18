"""Pipeline 与 GUI 之间通信的事件类型与统计。

`PipelineStats` 从 `douyin_dl/pipeline.py` 迁移至此，以避免
`progress.py` 反向 import `pipeline` 造成循环导入。
"""

from __future__ import annotations

import dataclasses
from typing import Callable, Optional


# 事件类型常量
EVENT_BATCH_STARTED = "batch_started"
EVENT_ITEM_STARTED = "item_started"
EVENT_STAGE = "stage"
EVENT_DOWNLOAD_PROGRESS = "download_progress"
EVENT_ITEM_FINISHED = "item_finished"
EVENT_AUTH_REQUIRED = "auth_required"
EVENT_AUTH_DONE = "auth_done"
EVENT_BATCH_FINISHED = "batch_finished"
EVENT_LOG = "log"


@dataclasses.dataclass
class PipelineStats:
    """Accumulator for run results.

    字段名与行为与原 `pipeline.py` 中的 `PipelineStats` 一致，
    仅迁移到本模块以便 `progress.py` 与 GUI 共享同一类型。
    """

    success: int = 0
    failed: int = 0
    skipped: int = 0
    failed_urls: list = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class ProgressEvent:
    """Pipeline 向 GUI 投递的进度事件。"""

    type: str
    url: str = ""
    index: int = 0
    total: int = 0
    stage: str = ""
    status: str = ""
    reason: str = ""
    downloaded: int = 0
    content_length: int = 0
    stats: Optional[PipelineStats] = None
    message: str = ""
    callback: Optional[Callable[[], None]] = None
