import asyncio
import contextlib
import logging
import time
from collections import deque
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


async def _default_alert_backend(
    title: str,
    detail: Dict[str, Any],
    mention: bool = True,
    table: bool = False,
    env: str = "",
    mention_users=None,
):
    """默认告警后端：写入 logging"""
    logger.warning(f"[ALERT] {title} | {detail}")


class AlertService:
    """
    异步告警服务

    通过 DI 容器管理生命周期，不再使用单例模式。
    通过构造函数传入自定义的 alert_backend 可接入飞书、钉钉、Slack 等。
    默认使用 logging.warning 输出。
    """

    def __init__(
        self,
        alert_backend: Optional[Callable] = None,
        max_queue_size: int = 1000,
    ):
        self._backend = alert_backend or _default_alert_backend
        self.queue: Optional[asyncio.Queue] = None
        self._worker_task: Optional[asyncio.Task] = None
        self._running = False
        self._max_queue_size = max_queue_size
        self._recent_alerts = deque(maxlen=200)
        self._dropped_count = 0

    async def start(self):
        if self._running:
            return

        self.queue = asyncio.Queue(maxsize=self._max_queue_size)
        self._running = True
        self._worker_task = asyncio.create_task(self._worker(), name="alert_service")
        logger.info("AlertService started")

    async def stop(self, drain_timeout: float = 5.0):
        if not self._running:
            return

        self._running = False

        if self.queue and self.queue.qsize() > 0:
            logger.info(f"AlertService draining {self.queue.qsize()} alerts...")
            try:
                await asyncio.wait_for(self.queue.join(), timeout=drain_timeout)
            except asyncio.TimeoutError:
                logger.warning(f"AlertService drain timeout, {self.queue.qsize()} alerts remaining")

        if self._worker_task:
            self._worker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker_task

        if self._dropped_count > 0:
            logger.warning(f"AlertService stopped, dropped alerts: {self._dropped_count}")

        self._worker_task = None
        self.queue = None

    async def send_alert(
        self,
        title: str,
        detail: Dict[str, Any],
        mention: bool = True,
        table: bool = False,
        env: str = "",
        mention_users=None,
        dedup_key: Optional[str] = None,
    ):
        if not self._running or self.queue is None:
            return

        if dedup_key and self._is_duplicate(dedup_key):
            return

        item = {
            "title": title,
            "detail": detail,
            "mention": mention,
            "table": table,
            "env": env,
            "mention_users": mention_users,
        }

        try:
            self.queue.put_nowait(item)
        except asyncio.QueueFull:
            self._dropped_count += 1
            logger.warning(f"Alert queue full, dropped alert: {title}")

    def _is_duplicate(self, dedup_key: str) -> bool:
        now = time.time()

        while self._recent_alerts and now - self._recent_alerts[0][1] > 60:
            self._recent_alerts.popleft()

        if any(key == dedup_key for key, _ in self._recent_alerts):
            logger.debug(f"Alert deduplicated: {dedup_key}")
            return True

        self._recent_alerts.append((dedup_key, now))
        return False

    async def _worker(self):
        while self._running:
            try:
                item = await self.queue.get()
                try:
                    await self._backend(
                        title=item["title"],
                        detail=item["detail"],
                        mention=item["mention"],
                        table=item["table"],
                        env=item["env"],
                        mention_users=item["mention_users"],
                    )
                except Exception as e:
                    logger.error(f"Failed to send alert: {e}")
                finally:
                    self.queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"AlertService worker error: {e}")

    def get_metrics(self) -> dict:
        return {
            "queue_size": self.queue.qsize() if self.queue else 0,
            "queue_maxsize": self.queue.maxsize if self.queue else 0,
            "dropped_count": self._dropped_count,
            "is_running": self._running,
        }
