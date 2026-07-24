"""Outbox Job - 轮询 index_outbox 并幂等更新 Chroma 索引"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from src.core.config import YggdrasilConfig
from src.core.yggdrasil.ports.repositories import OutboxRepository, RevisionRepository
from src.infra.observability import LogService
from src.infra.vector.chroma_index import ChromaIndexService

logger = logging.getLogger(__name__)


class OutboxJob:
    """Outbox 消费 Job"""

    def __init__(
        self,
        outbox_repo: OutboxRepository,
        config: YggdrasilConfig,
        log_service: Optional[LogService] = None,
        chroma_index: Optional[ChromaIndexService] = None,
        revision_repo: Optional[RevisionRepository] = None,
    ):
        self._outbox_repo = outbox_repo
        self._config = config
        self._log_service = log_service
        self._chroma_index = chroma_index
        self._revision_repo = revision_repo
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self, interval: float = 5.0):
        """启动轮询"""
        self._running = True
        self._task = asyncio.create_task(self._run_loop(interval))
        logger.info("OutboxJob started")

    async def stop(self, timeout: float = 10.0):
        """停止轮询"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await asyncio.wait_for(self._task, timeout=timeout)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
        logger.info("OutboxJob stopped")

    async def _run_loop(self, interval: float):
        while self._running:
            try:
                batch = await self._outbox_repo.claim(batch_size=10)
                for item in batch:
                    try:
                        await self._process_item(item)
                        await self._outbox_repo.mark_done(item["id"])
                    except Exception as e:
                        logger.error(f"Outbox item failed: {item['id']}, error={e}")
                        await self._outbox_repo.mark_failed(item["id"], str(e))
            except Exception as e:
                logger.warning(f"Outbox poll error: {e}")

            await asyncio.sleep(interval)

    async def _process_item(self, item):
        """处理单个 outbox 条目：更新 Chroma 索引"""
        aggregate_type = item.get("aggregate_type", "")
        aggregate_id = item.get("aggregate_id", "")
        operation = item.get("operation", "")
        logger.debug(f"Processing outbox item: {item['id']} ({aggregate_type}/{operation})")

        if not self._chroma_index or not self._revision_repo:
            logger.warning("ChromaIndex or RevisionRepo not configured, skipping outbox processing")
            return

        if aggregate_type == "node_revision":
            if operation == "upsert":
                rev = await self._revision_repo.get_node(aggregate_id)
                if rev:
                    await self._chroma_index.upsert_revision(rev)
            elif operation == "delete":
                await self._chroma_index.delete_revision(aggregate_id)
        elif aggregate_type == "edge_revision":
            # 边暂不索引到 Chroma
            pass
        else:
            logger.debug(f"Unknown aggregate_type: {aggregate_type}")
