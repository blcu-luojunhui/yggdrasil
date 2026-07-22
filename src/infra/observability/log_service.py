import asyncio
import contextlib
import json
import logging
import os
import sys
import time
from typing import Optional

logger = logging.getLogger(__name__)

# 关键事件类型，队列满时写入兜底文件
_CRITICAL_EVENT_TYPES = frozenset(
    {
        "node_update_failed",
        "edge_update_failed",
        "inspection_error",
        "pollution_detected",
    }
)


class LogService:
    """
    异步日志服务

    默认实现将日志输出到 Python logging。
    可通过继承并重写 _put_log 方法接入自定义后端（阿里云 SLS、ELK 等）。
    """

    def __init__(self, log_config=None):
        self.config = log_config
        self.queue: Optional[asyncio.Queue] = None
        self._worker_task: Optional[asyncio.Task] = None
        self._running = False
        self._dropped_count = 0
        self._last_drop_warn_time = 0
        self._fallback_file = ".logs/critical_events.jsonl"

    async def start(self):
        if self._running:
            return

        max_size = 10000
        if self.config and hasattr(self.config, "queue_size"):
            max_size = self.config.queue_size

        self.queue = asyncio.Queue(maxsize=max_size)
        self._running = True
        self._worker_task = asyncio.create_task(self._worker())
        logger.info("LogService started")

    async def stop(self, drain_timeout: float = 10.0):
        if not self._running:
            return

        self._running = False

        if self.queue and self.queue.qsize() > 0:
            remaining = self.queue.qsize()
            logger.info(f"LogService draining {remaining} pending logs...")
            try:
                await asyncio.wait_for(self._drain_remaining(), timeout=drain_timeout)
            except asyncio.TimeoutError:
                logger.warning(f"LogService drain timeout, {self.queue.qsize()} logs lost")

        if self._worker_task:
            self._worker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker_task

        if self._dropped_count > 0:
            logger.warning(f"LogService stopped, total dropped: {self._dropped_count}")

        self._worker_task = None
        self.queue = None

    async def _drain_remaining(self):
        while not self.queue.empty():
            try:
                contents = self.queue.get_nowait()
                await asyncio.to_thread(self._put_log, contents)
                self.queue.task_done()
            except asyncio.QueueEmpty:
                break
            except Exception as e:
                logger.error(f"LogService drain error: {e}")
                self.queue.task_done()

    def _write_fallback_log(self, contents: dict):
        """关键日志兜底写入本地文件"""
        try:
            os.makedirs(os.path.dirname(self._fallback_file), exist_ok=True)
            with open(self._fallback_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(contents, ensure_ascii=False, default=str) + "\n")
        except Exception as e:
            logger.error(f"Failed to write fallback log: {e}")

    async def log(self, contents: dict):
        if not self._running or self.queue is None:
            return

        try:
            self.queue.put_nowait(contents)
        except asyncio.QueueFull:
            self._dropped_count += 1

            event_type = contents.get("event_type", "")
            if event_type in _CRITICAL_EVENT_TYPES:
                self._write_fallback_log(contents)
                print(
                    f"[CRITICAL LOG DROPPED] {json.dumps(contents, ensure_ascii=False, default=str)}",
                    file=sys.stderr,
                )

            now = time.time()
            if now - self._last_drop_warn_time > 60:
                self._last_drop_warn_time = now
                logger.warning(f"LogService queue full, dropped {self._dropped_count} logs total")

    def get_metrics(self) -> dict:
        return {
            "queue_size": self.queue.qsize() if self.queue else 0,
            "queue_maxsize": self.queue.maxsize if self.queue else 0,
            "dropped_count": self._dropped_count,
            "is_running": self._running,
        }

    async def _worker(self):
        try:
            while self._running:
                contents = await self.queue.get()
                try:
                    await asyncio.to_thread(self._put_log, contents)
                except Exception as e:
                    logger.error(f"LogService put_log failed: {e}")
                finally:
                    self.queue.task_done()
        except asyncio.CancelledError:
            pass

    @staticmethod
    def _put_log(contents: dict):
        """
        日志写入后端（默认使用 Python logging）。

        重写此方法可接入自定义后端，例如：
        - 阿里云 SLS
        - Elasticsearch / Logstash
        - 文件系统
        """
        log_msg = json.dumps(contents, ensure_ascii=False, default=str)
        logger.info(log_msg)
