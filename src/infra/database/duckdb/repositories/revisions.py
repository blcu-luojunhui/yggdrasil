"""RevisionRepository — 节点/边修订持久化"""

import json
import logging
from datetime import datetime
from typing import List, Optional

from src.core.yggdrasil.cognitive.models import (
    EdgeRevision,
    NodeRevision,
    NodeStatus,
    RetrievalScope,
)
from src.infra.database.duckdb.pool import DuckDBPool

from . import _uuid_v7

logger = logging.getLogger(__name__)


class DuckDBRevisionRepository:
    """DuckDB 实现的 RevisionRepository"""

    def __init__(self, pool: DuckDBPool):
        self.pool = pool

    # ── Node Revision ──

    async def create_node(self, rev: NodeRevision) -> str:
        """创建节点修订（同时确保 cognitive_node 存在）"""
        revision_id = rev.revision_id or _uuid_v7()
        now = datetime.utcnow()

        # 确保 cognitive_node 存在
        await self.pool.async_save(
            """INSERT OR IGNORE INTO cognitive_node (node_id, tree_id, role, created_by, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (rev.node_id, rev.tree_id, rev.role, rev.author_id, now),
        )

        await self.pool.async_save(
            """INSERT INTO node_revision (
                   revision_id, node_id, tree_id, parent_revision_id, role,
                   title, summary, payload, status, utility, confidence,
                   freshness, risk, valid_from, valid_until, evidence_refs,
                   change_reason, author_type, author_id, content_hash, created_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                revision_id,
                rev.node_id,
                rev.tree_id,
                rev.parent_revision_id,
                rev.role,
                rev.title,
                rev.summary,
                json.dumps(rev.payload) if rev.payload else None,
                rev.status.value if isinstance(rev.status, NodeStatus) else rev.status,
                rev.utility,
                rev.confidence,
                rev.freshness,
                rev.risk,
                rev.valid_from,
                rev.valid_until,
                json.dumps(rev.evidence_refs) if rev.evidence_refs else "[]",
                rev.change_reason,
                rev.author_type,
                rev.author_id,
                rev.content_hash,
                now,
            ),
        )
        return revision_id

    async def create_edge(self, rev: EdgeRevision) -> str:
        """创建边修订（同时确保 cognitive_edge 存在）"""
        revision_id = rev.revision_id or _uuid_v7()
        now = datetime.utcnow()

        # 确保 cognitive_edge 存在
        await self.pool.async_save(
            """INSERT OR IGNORE INTO cognitive_edge (edge_id, tree_id, source_node_id, target_node_id, relation, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (rev.edge_id, rev.tree_id, rev.source_node_id, rev.target_node_id, rev.relation, now),
        )

        await self.pool.async_save(
            """INSERT INTO edge_revision (
                   revision_id, edge_id, tree_id, parent_revision_id,
                   source_node_id, target_node_id, relation, weight, confidence,
                   applicability, propagation_policy, evidence_refs,
                   valid_from, valid_until, status, created_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                revision_id,
                rev.edge_id,
                rev.tree_id,
                rev.parent_revision_id,
                rev.source_node_id,
                rev.target_node_id,
                rev.relation,
                rev.weight,
                rev.confidence,
                rev.applicability,
                rev.propagation_policy,
                json.dumps(rev.evidence_refs) if rev.evidence_refs else "[]",
                rev.valid_from,
                rev.valid_until,
                rev.status.value if isinstance(rev.status, NodeStatus) else rev.status,
                now,
            ),
        )
        return revision_id

    # ── Get ──

    async def get_node(self, revision_id: str) -> Optional[NodeRevision]:
        """按修订 ID 获取节点修订"""
        row = await self.pool.async_fetch_one(
            "SELECT * FROM node_revision WHERE revision_id = ?", (revision_id,)
        )
        return self._row_to_node_revision(row) if row else None

    async def get_edge(self, revision_id: str) -> Optional[EdgeRevision]:
        """按修订 ID 获取边修订"""
        row = await self.pool.async_fetch_one(
            "SELECT * FROM edge_revision WHERE revision_id = ?", (revision_id,)
        )
        return self._row_to_edge_revision(row) if row else None

    async def list_by_ids(self, revision_ids: List[str]) -> List[NodeRevision]:
        """批量获取节点修订"""
        if not revision_ids:
            return []
        # DuckDB 不支持 ? 数组绑定，构造占位符
        placeholders = ",".join("?" for _ in revision_ids)
        rows = await self.pool.async_fetch(
            f"SELECT * FROM node_revision WHERE revision_id IN ({placeholders})",
            tuple(revision_ids),
        )
        return [self._row_to_node_revision(r) for r in rows]

    async def list_active_for_ring(
        self, ring_id: str, scope: RetrievalScope
    ) -> List[NodeRevision]:
        """获取指定 Ring 的活动节点修订"""
        tree_ids = scope.tree_ids or []
        if tree_ids:
            placeholders = ",".join("?" for _ in tree_ids)
            rows = await self.pool.async_fetch(
                f"""SELECT nr.* FROM node_revision nr
                    INNER JOIN ring_node_revision rnr ON nr.revision_id = rnr.revision_id
                    WHERE rnr.ring_id = ? AND nr.tree_id IN ({placeholders})
                    ORDER BY nr.utility DESC
                    LIMIT ?""",
                (ring_id, *tree_ids, scope.max_nodes),
            )
        else:
            rows = await self.pool.async_fetch(
                """SELECT nr.* FROM node_revision nr
                   INNER JOIN ring_node_revision rnr ON nr.revision_id = rnr.revision_id
                   WHERE rnr.ring_id = ?
                   ORDER BY nr.utility DESC
                   LIMIT ?""",
                (ring_id, scope.max_nodes),
            )
        return [self._row_to_node_revision(r) for r in rows]

    async def list_edges_for_ring(self, ring_id: str) -> List[EdgeRevision]:
        """获取指定 Ring 的边修订"""
        rows = await self.pool.async_fetch(
            """SELECT er.* FROM edge_revision er
               INNER JOIN ring_edge_revision rer ON er.revision_id = rer.revision_id
               WHERE rer.ring_id = ?
               ORDER BY er.weight DESC""",
            (ring_id,),
        )
        return [self._row_to_edge_revision(r) for r in rows]

    async def get_latest_node_revision(self, node_id: str) -> Optional[NodeRevision]:
        """获取节点的最新修订"""
        row = await self.pool.async_fetch_one(
            "SELECT * FROM node_revision WHERE node_id = ? ORDER BY created_at DESC LIMIT 1",
            (node_id,),
        )
        return self._row_to_node_revision(row) if row else None

    async def get_latest_edge_revision(self, edge_id: str) -> Optional[EdgeRevision]:
        """获取边的最新修订"""
        row = await self.pool.async_fetch_one(
            "SELECT * FROM edge_revision WHERE edge_id = ? ORDER BY created_at DESC LIMIT 1",
            (edge_id,),
        )
        return self._row_to_edge_revision(row) if row else None

    async def list_all_active(
        self, tree_id: Optional[str] = None, limit: int = 10000, offset: int = 0
    ) -> List[NodeRevision]:
        """列出所有 active 状态的节点修订（支持按 tree_id 过滤）"""
        if tree_id:
            rows = await self.pool.async_fetch(
                "SELECT * FROM node_revision WHERE status = 'active' AND tree_id = ? ORDER BY created_at LIMIT ? OFFSET ?",
                (tree_id, limit, offset),
            )
        else:
            rows = await self.pool.async_fetch(
                "SELECT * FROM node_revision WHERE status = 'active' ORDER BY created_at LIMIT ? OFFSET ?",
                (limit, offset),
            )
        return [self._row_to_node_revision(r) for r in rows]

    # ── Row mappers ──

    @staticmethod
    def _row_to_node_revision(row: dict) -> NodeRevision:
        evidence_refs_raw = row.get("evidence_refs")
        return NodeRevision(
            revision_id=row["revision_id"],
            node_id=row["node_id"],
            tree_id=row["tree_id"],
            parent_revision_id=row.get("parent_revision_id"),
            role=row.get("role", "fact"),
            title=row.get("title", ""),
            summary=row.get("summary", ""),
            payload=json.loads(row["payload"]) if isinstance(row.get("payload"), str) else row.get("payload"),
            status=NodeStatus(row.get("status", "candidate")),
            utility=float(row.get("utility", 0.5)),
            confidence=float(row.get("confidence", 0.5)),
            freshness=float(row.get("freshness", 0.5)),
            risk=float(row.get("risk", 0.0)),
            valid_from=row.get("valid_from"),
            valid_until=row.get("valid_until"),
            evidence_refs=json.loads(evidence_refs_raw) if isinstance(evidence_refs_raw, str) else (evidence_refs_raw or []),
            change_reason=row.get("change_reason", ""),
            author_type=row.get("author_type", "system"),
            author_id=row.get("author_id", ""),
            content_hash=row.get("content_hash", ""),
            created_at=row.get("created_at"),
        )

    @staticmethod
    def _row_to_edge_revision(row: dict) -> EdgeRevision:
        evidence_refs_raw = row.get("evidence_refs")
        return EdgeRevision(
            revision_id=row["revision_id"],
            edge_id=row["edge_id"],
            tree_id=row["tree_id"],
            parent_revision_id=row.get("parent_revision_id"),
            source_node_id=row["source_node_id"],
            target_node_id=row["target_node_id"],
            relation=row.get("relation", "enables"),
            weight=float(row.get("weight", 0.5)),
            confidence=float(row.get("confidence", 0.5)),
            applicability=float(row.get("applicability", 1.0)),
            propagation_policy=row.get("propagation_policy", "default"),
            evidence_refs=json.loads(evidence_refs_raw) if isinstance(evidence_refs_raw, str) else (evidence_refs_raw or []),
            valid_from=row.get("valid_from"),
            valid_until=row.get("valid_until"),
            status=NodeStatus(row.get("status", "candidate")),
            created_at=row.get("created_at"),
        )
