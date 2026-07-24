"""RingRepository — Ring 生命周期与映射持久化"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from src.core.yggdrasil.cognitive.models import RingHealth, RingLifecycle
from src.infra.database.duckdb.pool import DuckDBPool

from . import _uuid_v7

logger = logging.getLogger(__name__)


class Ring(BaseModel):
    """Ring 模型（内部使用）"""
    ring_id: str
    tree_id: str
    sequence: int
    lifecycle_status: RingLifecycle = RingLifecycle.GROWING
    health_status: RingHealth = RingHealth.HEALTHY
    parent_ring_ids: List[str] = Field(default_factory=list)
    soil_checkpoint: Optional[str] = None
    ontology_version: str = "1"
    policy_version: str = "1"
    evaluation_report_ref: Optional[str] = None
    quality_metrics: Optional[Dict[str, Any]] = None
    content_hash: str = ""
    started_at: Optional[datetime] = None
    sealed_at: Optional[datetime] = None


class DuckDBRingRepository:
    """DuckDB 实现的 RingRepository"""

    def __init__(self, pool: DuckDBPool):
        self.pool = pool

    async def create(self, ring) -> str:
        """创建 Ring（接受 Ring 实例或 dict）"""
        ring_id = ring.get("ring_id") if isinstance(ring, dict) else getattr(ring, "ring_id", None)
        ring_id = ring_id or _uuid_v7()

        tree_id = ring["tree_id"] if isinstance(ring, dict) else ring.tree_id
        sequence = ring["sequence"] if isinstance(ring, dict) else ring.sequence
        lifecycle = ring.get("lifecycle_status", "growing") if isinstance(ring, dict) else getattr(ring, "lifecycle_status", "growing")
        health = ring.get("health_status", "healthy") if isinstance(ring, dict) else getattr(ring, "health_status", "healthy")
        parent_ids = ring.get("parent_ring_ids", []) if isinstance(ring, dict) else getattr(ring, "parent_ring_ids", [])
        soil_cp = ring.get("soil_checkpoint") if isinstance(ring, dict) else getattr(ring, "soil_checkpoint", None)
        ont_ver = ring.get("ontology_version", "1") if isinstance(ring, dict) else getattr(ring, "ontology_version", "1")
        pol_ver = ring.get("policy_version", "1") if isinstance(ring, dict) else getattr(ring, "policy_version", "1")
        eval_ref = ring.get("evaluation_report_ref") if isinstance(ring, dict) else getattr(ring, "evaluation_report_ref", None)
        quality = ring.get("quality_metrics") if isinstance(ring, dict) else getattr(ring, "quality_metrics", None)
        content_hash = ring.get("content_hash", "") if isinstance(ring, dict) else getattr(ring, "content_hash", "")
        now = datetime.utcnow()

        await self.pool.async_save(
            """INSERT INTO ring (ring_id, tree_id, sequence, lifecycle_status, health_status,
               parent_ring_ids, soil_checkpoint, ontology_version, policy_version,
               evaluation_report_ref, quality_metrics, content_hash, started_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                ring_id,
                tree_id,
                sequence,
                isinstance(lifecycle, RingLifecycle) and lifecycle.value or lifecycle,
                isinstance(health, RingHealth) and health.value or health,
                json.dumps(parent_ids) if parent_ids else "[]",
                soil_cp,
                ont_ver,
                pol_ver,
                eval_ref,
                json.dumps(quality) if quality else None,
                content_hash,
                now,
            ),
        )
        return ring_id

    async def get(self, ring_id: str) -> Optional[Any]:
        """获取 Ring 信息（返回 dict）"""
        row = await self.pool.async_fetch_one(
            "SELECT * FROM ring WHERE ring_id = ?", (ring_id,)
        )
        if not row:
            return None
        result = dict(row)
        # JSON 字段反序列化
        parent_raw = result.get("parent_ring_ids")
        if isinstance(parent_raw, str):
            result["parent_ring_ids"] = json.loads(parent_raw)
        quality_raw = result.get("quality_metrics")
        if isinstance(quality_raw, str):
            result["quality_metrics"] = json.loads(quality_raw)
        return result

    async def add_node_mapping(self, ring_id: str, node_id: str, revision_id: str) -> None:
        """添加节点映射"""
        await self.pool.async_save(
            "INSERT OR IGNORE INTO ring_node_revision (ring_id, node_id, revision_id) VALUES (?, ?, ?)",
            (ring_id, node_id, revision_id),
        )

    async def add_edge_mapping(self, ring_id: str, edge_id: str, revision_id: str) -> None:
        """添加边映射"""
        await self.pool.async_save(
            "INSERT OR IGNORE INTO ring_edge_revision (ring_id, edge_id, revision_id) VALUES (?, ?, ?)",
            (ring_id, edge_id, revision_id),
        )

    async def get_node_mappings(self, ring_id: str) -> Dict[str, str]:
        """获取节点映射字典（node_id -> revision_id）"""
        rows = await self.pool.async_fetch(
            "SELECT node_id, revision_id FROM ring_node_revision WHERE ring_id = ?",
            (ring_id,),
        )
        return {r["node_id"]: r["revision_id"] for r in rows}

    async def get_edge_mappings(self, ring_id: str) -> Dict[str, str]:
        """获取边映射字典（edge_id -> revision_id）"""
        rows = await self.pool.async_fetch(
            "SELECT edge_id, revision_id FROM ring_edge_revision WHERE ring_id = ?",
            (ring_id,),
        )
        return {r["edge_id"]: r["revision_id"] for r in rows}

    async def seal(self, ring_id: str) -> None:
        """密封 Ring（标记为 sealed）"""
        await self.pool.async_save(
            "UPDATE ring SET lifecycle_status = 'sealed', sealed_at = CURRENT_TIMESTAMP WHERE ring_id = ?",
            (ring_id,),
        )

    async def activate(self, ring_id: str) -> None:
        """激活 Ring（设为 active 状态）"""
        await self.pool.async_save(
            "UPDATE ring SET lifecycle_status = 'active' WHERE ring_id = ?",
            (ring_id,),
        )

    async def rollback(self, ring_id: str) -> None:
        """回滚目标 Ring — 不修改 ring 状态，仅校验存在"""
        row = await self.pool.async_fetch_one(
            "SELECT ring_id FROM ring WHERE ring_id = ?", (ring_id,)
        )
        if not row:
            raise ValueError(f"Ring not found: {ring_id}")

    async def set_health(self, ring_id: str, health: RingHealth) -> None:
        """设置 Ring 健康状态"""
        await self.pool.async_save(
            "UPDATE ring SET health_status = ? WHERE ring_id = ?",
            (health.value if isinstance(health, RingHealth) else health, ring_id),
        )
