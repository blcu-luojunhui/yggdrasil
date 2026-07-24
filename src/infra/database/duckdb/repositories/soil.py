"""SoilRepository — 土壤事件持久化（追加写的事实源）"""

import json
import logging
from datetime import datetime
from typing import List, Optional

from src.core.yggdrasil.soil.models import SoilEvent
from src.infra.database.duckdb.pool import DuckDBPool

from . import _uuid_v7

logger = logging.getLogger(__name__)


class DuckDBSoilRepository:
    """DuckDB 实现的 SoilRepository"""

    def __init__(self, pool: DuckDBPool):
        self.pool = pool

    async def append_event(self, event: SoilEvent) -> str:
        """追加写入一个土壤事件"""
        event_id = event.event_id or _uuid_v7()
        now = datetime.utcnow()

        await self.pool.async_save(
            """INSERT INTO soil_event (
                   event_id, event_type, tenant_id, actor_id, subject_id, source_type,
                   source_ref, payload, observed_at, ingested_at, valid_from,
                   valid_until, trust_level, integrity_hash, access_scope,
                   contamination_status, correlation_id, causation_id,
                   idempotency_key
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event_id,
                event.event_type,
                event.tenant_id,
                event.actor_id,
                event.subject_id,
                event.source_type,
                event.source_ref,
                json.dumps(event.payload) if event.payload else None,
                event.observed_at or now,
                now,
                event.valid_from,
                event.valid_until,
                event.trust_level,
                event.integrity_hash,
                event.access_scope,
                event.contamination_status,
                event.correlation_id,
                event.causation_id,
                event.idempotency_key,
            ),
        )
        return event_id

    async def get_event(self, event_id: str) -> Optional[SoilEvent]:
        """按 ID 获取事件"""
        row = await self.pool.async_fetch_one(
            "SELECT * FROM soil_event WHERE event_id = ?", (event_id,)
        )
        return self._row_to_event(row) if row else None

    async def get_event_by_idempotency_key(
        self, tenant_id: str, idempotency_key: str
    ) -> Optional[SoilEvent]:
        """按幂等键查找事件"""
        row = await self.pool.async_fetch_one(
            "SELECT * FROM soil_event WHERE tenant_id = ? AND idempotency_key = ?",
            (tenant_id, idempotency_key),
        )
        return self._row_to_event(row) if row else None

    async def list_after_checkpoint(self, checkpoint: int, limit: int = 100) -> List[SoilEvent]:
        """获取指定 checkpoint 之后的事件"""
        rows = await self.pool.async_fetch(
            "SELECT * FROM soil_event WHERE checkpoint > ? ORDER BY checkpoint ASC LIMIT ?",
            (checkpoint, limit),
        )
        return [self._row_to_event(r) for r in rows]

    @staticmethod
    def _row_to_event(row: dict) -> SoilEvent:
        return SoilEvent(
            event_id=row["event_id"],
            event_type=row["event_type"],
            tenant_id=row.get("tenant_id", "default"),
            actor_id=row.get("actor_id", ""),
            subject_id=row.get("subject_id", ""),
            source_type=row.get("source_type", ""),
            source_ref=row.get("source_ref", ""),
            payload=json.loads(row["payload"]) if isinstance(row.get("payload"), str) else row.get("payload"),
            observed_at=row.get("observed_at"),
            ingested_at=row.get("ingested_at"),
            valid_from=row.get("valid_from"),
            valid_until=row.get("valid_until"),
            trust_level=float(row.get("trust_level", 0.5)),
            integrity_hash=row.get("integrity_hash", ""),
            access_scope=row.get("access_scope", "default"),
            contamination_status=row.get("contamination_status", "clean"),
            correlation_id=row.get("correlation_id"),
            causation_id=row.get("causation_id"),
            idempotency_key=row.get("idempotency_key", ""),
            checkpoint=row.get("checkpoint", 0),
        )
