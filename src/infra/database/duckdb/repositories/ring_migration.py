"""Ring 0 迁移 - 将旧 cog_node/cog_edge 迁移到新版本化结构"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Optional

from src.core.yggdrasil.cognitive.models import NodeStatus
from src.infra.database.duckdb.pool import DuckDBPool
from src.infra.database.duckdb.repositories import _uuid_v7

logger = logging.getLogger(__name__)


class RingMigration:
    """Ring 0 迁移器（幂等）"""

    def __init__(self, pool: DuckDBPool):
        self.pool = pool

    async def migrate(self) -> dict:
        """执行 Ring 0 迁移

        Returns:
            迁移统计：{trees_created, nodes_migrated, edges_migrated, ring_0_created}
        """
        stats = {"trees_created": 0, "nodes_migrated": 0, "edges_migrated": 0, "ring_0_created": 0}

        # 1. 创建默认 Tree
        diag_tree_id = await self._ensure_tree("database-diagnostics", "database diagnostics")
        shared_tree_id = await self._ensure_tree("shared-foundation", "shared security and output specs")
        if diag_tree_id:
            stats["trees_created"] += 1
        if shared_tree_id:
            stats["trees_created"] += 1

        # 2. 迁移旧 cog_node -> cognitive_node + node_revision
        old_nodes = await self.pool.async_fetch("SELECT * FROM cog_node ORDER BY created_at")
        for old in old_nodes:
            node_id = old["id"]
            tree_id = self._resolve_tree(old.get("domain_path", ""), diag_tree_id, shared_tree_id)

            existing = await self.pool.async_fetch_one(
                "SELECT node_id FROM cognitive_node WHERE node_id = ?", (node_id,)
            )
            if existing:
                continue

            await self.pool.async_save(
                """INSERT INTO cognitive_node (node_id, tree_id, domain_id, domain_path, role, created_by)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (node_id, tree_id, old.get("domain_id"), old.get("domain_path", ""),
                 old.get("role", "fact"), "system"),
            )

            old_strength = float(old.get("strength", 0.5))
            old_health = float(old.get("health", 1.0))
            content = old.get("content") or ""
            content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

            revision_id = _uuid_v7()
            await self.pool.async_save(
                """INSERT INTO node_revision
                   (revision_id, node_id, tree_id, role, title, summary, payload, status,
                    utility, confidence, freshness, risk, content_hash, change_reason, author_type)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (revision_id, node_id, tree_id, old.get("role", "fact"),
                 old.get("title", ""), content[:500] if content else "", None,
                 NodeStatus.ACTIVE.value, old_strength, old_health, 0.5, 0.0,
                 content_hash, "Ring 0 migration", "system"),
            )
            stats["nodes_migrated"] += 1

        # 3. 迁移旧 cog_edge -> cognitive_edge + edge_revision
        old_edges = await self.pool.async_fetch("SELECT * FROM cog_edge ORDER BY created_at")
        for old in old_edges:
            edge_id = old["id"]
            source_node = await self.pool.async_fetch_one(
                "SELECT tree_id FROM cognitive_node WHERE node_id = ?", (old["source_id"],)
            )
            if not source_node:
                continue
            tree_id = source_node["tree_id"]

            existing = await self.pool.async_fetch_one(
                "SELECT edge_id FROM cognitive_edge WHERE edge_id = ?", (edge_id,)
            )
            if existing:
                continue

            await self.pool.async_save(
                """INSERT INTO cognitive_edge (edge_id, tree_id, source_node_id, target_node_id, relation)
                   VALUES (?, ?, ?, ?, ?)""",
                (edge_id, tree_id, old["source_id"], old["target_id"], old.get("relation", "enables")),
            )

            revision_id = _uuid_v7()
            await self.pool.async_save(
                """INSERT INTO edge_revision
                   (revision_id, edge_id, tree_id, source_node_id, target_node_id,
                    relation, weight, confidence, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (revision_id, edge_id, tree_id, old["source_id"], old["target_id"],
                 old.get("relation", "enables"), float(old.get("strength", 0.5)), 0.5,
                 NodeStatus.ACTIVE.value),
            )
            stats["edges_migrated"] += 1

        # 4. 创建 Ring 0 并建立 mapping
        for tree_id_name in [(diag_tree_id, "database-diagnostics"), (shared_tree_id, "shared-foundation")]:
            tree_id = tree_id_name[0]
            if not tree_id:
                continue

            existing_ring = await self.pool.async_fetch_one(
                "SELECT ring_id FROM ring WHERE tree_id = ? AND sequence = 0", (tree_id,)
            )
            if existing_ring:
                stats["ring_0_created"] += 1
                continue

            ring_id = _uuid_v7()
            await self.pool.async_save(
                """INSERT INTO ring (ring_id, tree_id, sequence, lifecycle_status, health_status,
                   ontology_version, content_hash)
                   VALUES (?, ?, 0, 'sealed', 'healthy', '1', ?)""",
                (ring_id, tree_id, hashlib.sha256(f"ring0-{tree_id}".encode()).hexdigest()),
            )

            nodes = await self.pool.async_fetch(
                """SELECT nr.node_id, nr.revision_id FROM node_revision nr
                   JOIN cognitive_node cn ON nr.node_id = cn.node_id
                   WHERE cn.tree_id = ? AND nr.status = ?""",
                (tree_id, NodeStatus.ACTIVE.value),
            )
            for n in nodes:
                await self.pool.async_save(
                    "INSERT OR IGNORE INTO ring_node_revision (ring_id, node_id, revision_id) VALUES (?, ?, ?)",
                    (ring_id, n["node_id"], n["revision_id"]),
                )

            edges = await self.pool.async_fetch(
                """SELECT er.edge_id, er.revision_id FROM edge_revision er
                   JOIN cognitive_edge ce ON er.edge_id = ce.edge_id
                   WHERE ce.tree_id = ? AND er.status = ?""",
                (tree_id, NodeStatus.ACTIVE.value),
            )
            for e in edges:
                await self.pool.async_save(
                    "INSERT OR IGNORE INTO ring_edge_revision (ring_id, edge_id, revision_id) VALUES (?, ?, ?)",
                    (ring_id, e["edge_id"], e["revision_id"]),
                )

            await self.pool.async_save(
                "UPDATE tree SET active_ring_id = ? WHERE tree_id = ?",
                (ring_id, tree_id),
            )
            stats["ring_0_created"] += 1
            logger.info(f"Ring 0 created for tree {tree_id_name[1]}: {ring_id}")

        logger.info(f"Migration complete: {json.dumps(stats)}")
        return stats

    async def _ensure_tree(self, name: str, bounded_context: str) -> Optional[str]:
        existing = await self.pool.async_fetch_one(
            "SELECT tree_id FROM tree WHERE name = ?", (name,)
        )
        if existing:
            return existing["tree_id"]
        tree_id = _uuid_v7()
        await self.pool.async_save(
            """INSERT INTO tree (tree_id, tenant_id, name, bounded_context, owner, status)
               VALUES (?, 'default', ?, ?, 'system', 'active')""",
            (tree_id, name, bounded_context),
        )
        logger.info(f"Tree created: {name} ({tree_id})")
        return tree_id

    @staticmethod
    def _resolve_tree(domain_path: str, diag_id: str, shared_id: str) -> str:
        path_lower = domain_path.lower()
        if any(kw in path_lower for kw in ["database", "sql", "query", "db"]):
            return diag_id
        return shared_id
