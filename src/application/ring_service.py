"""Ring 服务 - 年轮发布管理（原子事务 activate/rollback）"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from src.core.yggdrasil.cognitive.models import RingLifecycle
from src.core.yggdrasil.ports.repositories import (
    RevisionRepository,
    RingRepository,
    TreeRepository,
)
from src.core.yggdrasil.policies.release_gate import ReleaseGate, ReleaseGateResult
from src.infra.database.duckdb.pool import DuckDBPool
from src.infra.observability import MetricsCollector

logger = logging.getLogger(__name__)


class RingService:
    """Ring 发布服务 — 原子 activate/rollback"""

    def __init__(
        self,
        tree_repo: TreeRepository,
        ring_repo: RingRepository,
        revision_repo: RevisionRepository,
        pool: Optional[DuckDBPool] = None,
        release_gate: Optional[ReleaseGate] = None,
        metrics: Optional[MetricsCollector] = None,
    ):
        self._tree_repo = tree_repo
        self._ring_repo = ring_repo
        self._revision_repo = revision_repo
        self._pool = pool
        self._release_gate = release_gate or ReleaseGate(require_evidence=True)
        self._metrics = metrics
        self._locks: dict[str, asyncio.Lock] = {}

    def _get_lock(self, tree_id: str) -> asyncio.Lock:
        if tree_id not in self._locks:
            self._locks[tree_id] = asyncio.Lock()
        return self._locks[tree_id]

    async def seal(self, ring_id: str) -> ReleaseGateResult:
        """封存 Ring（执行门禁检查）"""
        ring = await self._ring_repo.get(ring_id)
        if not ring:
            return ReleaseGateResult(passed=False, reasons=["Ring not found"])

        node_mappings = await self._ring_repo.get_node_mappings(ring_id)
        edge_mappings = await self._ring_repo.get_edge_mappings(ring_id)

        revision_ids = list(node_mappings.values())
        edge_revision_ids = list(edge_mappings.values())

        node_revisions = await self._revision_repo.list_by_ids(revision_ids)
        edge_revisions = await self._revision_repo.list_by_ids(edge_revision_ids)

        result = await self._release_gate.check(ring, node_revisions, edge_revisions)
        if result.passed:
            await self._ring_repo.seal(ring_id)
            logger.info(f"Ring sealed: {ring_id}")
        else:
            logger.warning(f"Release gate failed for ring {ring_id}: {result.reasons}")
            if self._metrics:
                self._metrics.increment_release_gate_failed()

        return result

    async def activate(self, ring_id: str) -> None:
        """激活 Ring — 原子事务完成 ring 状态更新 + tree.active_ring_id 更新"""
        ring = await self._ring_repo.get(ring_id)
        if not ring:
            raise ValueError(f"Ring not found: {ring_id}")

        tree_id = ring.get("tree_id") if isinstance(ring, dict) else ring.tree_id
        lifecycle = ring.get("lifecycle_status") if isinstance(ring, dict) else ring.lifecycle_status

        if isinstance(lifecycle, RingLifecycle):
            lifecycle = lifecycle.value
        if lifecycle != "sealed":
            raise ValueError(f"Ring {ring_id} must be sealed before activation, current: {lifecycle}")

        health = ring.get("health_status") if isinstance(ring, dict) else ring.health_status
        if hasattr(health, "value"):
            health = health.value
        if health not in ("healthy",):
            raise ValueError(f"Ring {ring_id} health is {health}, must be healthy to activate")

        async with self._get_lock(tree_id):
            if self._pool:
                async with self._pool.transaction() as tx:
                    await tx.execute(
                        "UPDATE ring SET lifecycle_status = 'active' WHERE ring_id = ?",
                        (ring_id,),
                    )
                    await tx.execute(
                        "UPDATE tree SET active_ring_id = ?, updated_at = CURRENT_TIMESTAMP WHERE tree_id = ?",
                        (ring_id, tree_id),
                    )
                    logger.info(
                        f"Ring activated: {ring_id} (tree={tree_id}) [atomic]"
                    )
            else:
                await self._ring_repo.activate(ring_id)
                await self._tree_repo.update_active_ring(tree_id, ring_id)
                logger.info(f"Ring activated: {ring_id} (tree={tree_id})")

        if self._metrics:
            self._metrics.increment_ring_activation()

    async def rollback(self, tree_id: str, target_ring_id: str) -> None:
        """回滚到目标 Ring — 仅切换 active pointer，不修改历史 ring 状态"""
        target_ring = await self._ring_repo.get(target_ring_id)
        if not target_ring:
            raise ValueError(f"Target ring not found: {target_ring_id}")

        async with self._get_lock(tree_id):
            if self._pool:
                async with self._pool.transaction() as tx:
                    await tx.execute(
                        "UPDATE tree SET active_ring_id = ?, updated_at = CURRENT_TIMESTAMP WHERE tree_id = ?",
                        (target_ring_id, tree_id),
                    )
                    logger.info(
                        f"Tree {tree_id} rolled back to ring {target_ring_id} [atomic]"
                    )
            else:
                await self._ring_repo.rollback(target_ring_id)
                await self._tree_repo.update_active_ring(tree_id, target_ring_id)
                logger.info(f"Tree {tree_id} rolled back to ring {target_ring_id}")

        if self._metrics:
            self._metrics.increment_ring_rollback()