"""Soil 服务 - 事件追加和证据管理"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.core.yggdrasil.ports.repositories import SoilRepository
from src.core.yggdrasil.soil.models import SoilEvent
from src.infra.observability import MetricsCollector

logger = logging.getLogger(__name__)


def _compute_hash(payload: Optional[Dict[str, Any]]) -> str:
    """对 canonical JSON 计算 SHA-256"""
    if payload is None:
        return hashlib.sha256(b"null").hexdigest()
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class SoilService:
    """土壤事件服务"""

    def __init__(
        self,
        soil_repo: SoilRepository,
        metrics: Optional[MetricsCollector] = None,
    ):
        self._soil_repo = soil_repo
        self._metrics = metrics

    async def append_event(
        self,
        event_type: str,
        payload: Dict[str, Any],
        tenant_id: str = "default",
        source_type: str = "",
        source_ref: str = "",
        actor_id: str = "",
        idempotency_key: str = "",
        valid_from: Optional[datetime] = None,
        valid_until: Optional[datetime] = None,
        subject_id: str = "",
        observed_at: Optional[datetime] = None,
        correlation_id: Optional[str] = None,
        causation_id: Optional[str] = None,
        access_scope: str = "default",
        trust_level: float = 0.5,
    ) -> str:
        """追加事件（幂等）

        同一 tenant_id + idempotency_key 重复请求返回已有 event_id。
        payload 不同时抛出 IDEMPOTENCY_CONFLICT。
        """
        integrity_hash = _compute_hash(payload)
        now = datetime.now(timezone.utc)

        effective_key = idempotency_key or f"{event_type}_{now.timestamp()}"

        # 幂等检查：检查同 tenant_id + idempotency_key 是否已存在
        existing = await self._soil_repo.get_event_by_idempotency_key(tenant_id, effective_key)
        if existing:
            existing_hash = existing.integrity_hash
            if existing_hash and existing_hash != integrity_hash:
                raise ValueError(
                    f"IDEMPOTENCY_CONFLICT: same idempotency_key {effective_key} "
                    f"with different payload hash"
                )
            logger.info(f"Soil event idempotent return: {existing.event_id}")
            return existing.event_id

        event = SoilEvent(
            event_id="",  # repository 生成
            event_type=event_type,
            tenant_id=tenant_id,
            subject_id=subject_id,
            actor_id=actor_id,
            source_type=source_type,
            source_ref=source_ref,
            payload=payload,
            observed_at=observed_at or valid_from or now,
            ingested_at=now,
            valid_from=valid_from or now,
            valid_until=valid_until,
            access_scope=access_scope,
            trust_level=trust_level,
            correlation_id=correlation_id,
            causation_id=causation_id,
            integrity_hash=integrity_hash,
            idempotency_key=effective_key,
        )

        event_id = await self._soil_repo.append_event(event)
        logger.info(f"Soil event appended: {event_id} (type={event_type})")

        if self._metrics:
            self._metrics.increment_soil_event(event_type)

        return event_id

    async def get_event(self, event_id: str) -> Optional[SoilEvent]:
        return await self._soil_repo.get_event(event_id)

    async def list_events(
        self, checkpoint: int = 0, limit: int = 100
    ) -> List[SoilEvent]:
        return await self._soil_repo.list_after_checkpoint(checkpoint, limit)
