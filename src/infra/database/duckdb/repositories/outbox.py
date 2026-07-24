"""OutboxRepository — 索引 outbox 持久化（发件箱模式）"""

import hashlib
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.infra.database.duckdb.pool import DuckDBPool

from . import _uuid_v7

logger = logging.getLogger(__name__)


class DuckDBOutboxRepository:
    """DuckDB 实现的 OutboxRepository"""

    def __init__(self, pool: DuckDBPool):
        self.pool = pool

    async def enqueue(
        self,
        aggregate_type: str,
        aggregate_id: str,
        operation: str,
        payload: Optional[Dict] = None,
    ) -> str:
        """将消息加入 outbox"""
        outbox_id = _uuid_v7()
        now = datetime.utcnow()

        payload_str = json.dumps(payload) if payload else None
        payload_hash = ""
        if payload_str:
            payload_hash = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()

        await self.pool.async_save(
            """INSERT INTO index_outbox (
                   id, aggregate_type, aggregate_id, operation,
                   payload_hash, status, available_at
               ) VALUES (?, ?, ?, ?, ?, 'pending', ?)""",
            (outbox_id, aggregate_type, aggregate_id, operation, payload_hash, now),
        )
        return outbox_id

    async def claim(self, batch_size: int = 10) -> List[Any]:
        """获取一批待处理消息（标记为 processing）"""
        now = datetime.utcnow()

        # 使用事务确保原子性
        async with self.pool.transaction() as tx:
            rows = await tx.fetch_all(
                """SELECT * FROM index_outbox
                   WHERE status = 'pending' AND available_at <= ?
                   ORDER BY available_at ASC
                   LIMIT ?""",
                (now, batch_size),
            )

            if not rows:
                return []

            ids = [r["id"] for r in rows]
            placeholders = ",".join("?" for _ in ids)
            await tx.execute(
                f"UPDATE index_outbox SET status = 'processing', attempts = attempts + 1 WHERE id IN ({placeholders})",
                tuple(ids),
            )

        return rows

    async def mark_done(self, outbox_id: str) -> None:
        """标记为处理成功"""
        await self.pool.async_save(
            "UPDATE index_outbox SET status = 'done', processed_at = CURRENT_TIMESTAMP WHERE id = ?",
            (outbox_id,),
        )

    async def mark_failed(self, outbox_id: str, error: str) -> None:
        """标记为处理失败"""
        await self.pool.async_save(
            "UPDATE index_outbox SET status = 'failed', last_error = ? WHERE id = ?",
            (error, outbox_id),
        )
