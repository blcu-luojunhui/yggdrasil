"""TreeRepository — 树清单持久化"""

import json
import logging
from datetime import datetime
from typing import List, Optional

from src.core.yggdrasil.cognitive.models import TreeManifest
from src.infra.database.duckdb.pool import DuckDBPool

from . import _uuid_v7

logger = logging.getLogger(__name__)


class DuckDBTreeRepository:
    """DuckDB 实现的 TreeRepository"""

    def __init__(self, pool: DuckDBPool):
        self.pool = pool

    async def create(self, tree: TreeManifest) -> str:
        """创建一棵树"""
        tree_id = tree.tree_id or _uuid_v7()
        now = datetime.utcnow()
        await self.pool.async_save(
            """INSERT INTO tree (tree_id, tenant_id, name, bounded_context, owner,
               ontology_version, active_ring_id, capabilities, access_policy,
               retrieval_policy, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                tree_id,
                tree.tenant_id,
                tree.name,
                tree.bounded_context,
                tree.owner,
                tree.ontology_version,
                tree.active_ring_id,
                json.dumps(tree.capabilities) if tree.capabilities else "[]",
                tree.access_policy,
                tree.retrieval_policy,
                tree.status,
                now,
                now,
            ),
        )
        return tree_id

    async def get(self, tree_id: str) -> Optional[TreeManifest]:
        """按 ID 获取树清单"""
        row = await self.pool.async_fetch_one(
            "SELECT * FROM tree WHERE tree_id = ?", (tree_id,)
        )
        return self._row_to_manifest(row) if row else None

    async def list(self, tenant_id: str = "default") -> List[TreeManifest]:
        """列出租户下的所有树"""
        rows = await self.pool.async_fetch(
            "SELECT * FROM tree WHERE tenant_id = ? ORDER BY created_at", (tenant_id,)
        )
        return [self._row_to_manifest(r) for r in rows]

    async def update_active_ring(self, tree_id: str, ring_id: str) -> None:
        """更新树的活动 Ring ID"""
        await self.pool.async_save(
            "UPDATE tree SET active_ring_id = ?, updated_at = CURRENT_TIMESTAMP WHERE tree_id = ?",
            (ring_id, tree_id),
        )

    @staticmethod
    def _row_to_manifest(row: dict) -> TreeManifest:
        caps = row.get("capabilities")
        return TreeManifest(
            tree_id=row["tree_id"],
            tenant_id=row.get("tenant_id", "default"),
            name=row["name"],
            bounded_context=row.get("bounded_context", ""),
            owner=row.get("owner", ""),
            ontology_version=row.get("ontology_version", "1"),
            active_ring_id=row.get("active_ring_id"),
            capabilities=json.loads(caps) if isinstance(caps, str) else (caps or []),
            access_policy=row.get("access_policy", "default"),
            retrieval_policy=row.get("retrieval_policy", "default"),
            status=row.get("status", "active"),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )
