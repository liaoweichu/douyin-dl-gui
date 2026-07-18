"""后台线程：把 DownloadPipeline 跑在子线程，事件投递到 queue.Queue 给主线程消费。"""

from __future__ import annotations

import queue
import threading
from typing import Optional

from douyin_dl.models import Config
from douyin_dl.pipeline import DownloadPipeline
from douyin_dl.progress import (
    EVENT_DOWNLOAD_PROGRESS,
    PipelineStats,
    ProgressEvent,
)


class WorkerThread(threading.Thread):
    """在后台线程运行 DownloadPipeline，把进度事件投递到 event_queue。"""

    def __init__(
        self,
        urls: list[str],
        config: Config,
        event_queue: "queue.Queue[ProgressEvent]",
        cancel_event: threading.Event,
        pipeline: Optional[DownloadPipeline] = None,
    ) -> None:
        super().__init__(daemon=True)
        self._urls = urls
        self._config = config
        self._event_queue = event_queue
        self._cancel_event = cancel_event
        self._pipeline = pipeline
        self._stats: Optional[PipelineStats] = None

    def run(self) -> None:
        """线程入口：构造（或复用）Pipeline 并运行，捕获所有异常避免线程崩溃。"""
        try:
            pipeline = self._pipeline
            if pipeline is None:
                pipeline = DownloadPipeline(
                    config=self._config,
                    progress_callback=self._event_queue.put,
                    cancel_event=self._cancel_event,
                    download_progress_callback=self._on_download_progress,
                )
            self._stats = pipeline.run(self._urls)
        except Exception as e:
            self._event_queue.put(
                ProgressEvent(type="log", message=f"Worker 异常: {e}")
            )

    def _on_download_progress(
        self, url: str, downloaded: int, total: int
    ) -> None:
        """把 Pipeline 的下载进度回调适配为 ProgressEvent 投递到 event_queue。"""
        self._event_queue.put(
            ProgressEvent(
                type=EVENT_DOWNLOAD_PROGRESS,
                url=url,
                downloaded=downloaded,
                content_length=total,
            )
        )

    @property
    def stats(self) -> Optional[PipelineStats]:
        """返回 Pipeline.run 的统计结果（运行结束前为 None）。"""
        return self._stats
