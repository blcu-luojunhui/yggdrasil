import logging
import json
from typing import List, Optional, Dict, Set
from datetime import datetime

from src.core.config import YggdrasilConfig
from src.core.yggdrasil.models import (
    Domain,
    CognitiveNode,
    CognitiveEdge,
    CognitiveRole,
    RelationType,
    Season,
    ChangeLogEntry,
)
from src.infra.database.duckdb import DuckDBPool

logger = logging.getLogger(__name__)


class YggdrasilStore:
    """Yggdrasil 存储层 - DuckDB 持久化领域、边、变更日志、沙盒"""

    def __init__(self, db: DuckDBPool, config: YggdrasilConfig):
        self.db = db
        self.config = config

    async def ensure_skeleton(self) -> None:
        """确保基础骨架存在，创建表结构和根领域"""
        await self._create_tables()

        existing = await self.db.async_fetch_one("SELECT id FROM domains WHERE full_path = ''")
        if not existing:
            await self.db.async_save(
                "INSERT INTO domains (parent_id, domain_name, full_path, depth, season) VALUES (NULL, 'root', '', 0, 'spring')"
            )
            logger.info("Yggdrasil root domain created")

    async def _create_tables(self):
        """创建数据库表（如果不存在）"""
        await self.db.async_execute("""
            CREATE TABLE IF NOT EXISTS domains (
                id INTEGER PRIMARY KEY,
                parent_id INTEGER,
                domain_name VARCHAR NOT NULL,
                full_path VARCHAR NOT NULL UNIQUE,
                depth INTEGER NOT NULL DEFAULT 1,
                season VARCHAR NOT NULL DEFAULT 'spring',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (parent_id) REFERENCES domains(id) ON DELETE CASCADE
            )
        """)
        await self.db.async_execute("""
            CREATE TABLE IF NOT EXISTS cog_edges (
                id INTEGER PRIMARY KEY,
                from_node_id VARCHAR NOT NULL,
                to_node_id VARCHAR NOT NULL,
                relation_type VARCHAR NOT NULL,
                strength DOUBLE NOT NULL DEFAULT 0.5,
                source VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(from_node_id, to_node_id, relation_type)
            )
        """)
        await self.db.async_execute("""
            CREATE TABLE IF NOT EXISTS cog_change_log (
                id INTEGER PRIMARY KEY,
                node_id VARCHAR,
                edge_id INTEGER,
                operation VARCHAR NOT NULL,
                old_values JSON,
                new_values JSON,
                reason VARCHAR,
                trace_id VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await self.db.async_execute("""
            CREATE TABLE IF NOT EXISTS sandboxes (
                id INTEGER PRIMARY KEY,
                base_domain_id INTEGER NOT NULL,
                sandbox_name VARCHAR NOT NULL,
                status VARCHAR NOT NULL DEFAULT 'active',
                created_by VARCHAR,
                assessment_result BOOLEAN,
                assessment_reason TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                FOREIGN KEY (base_domain_id) REFERENCES domains(id) ON DELETE CASCADE
            )
        """)
        await self.db.async_execute("""
            CREATE TABLE IF NOT EXISTS sandbox_node_changes (
                id INTEGER PRIMARY KEY,
                sandbox_id INTEGER NOT NULL,
                node_id VARCHAR,
                change_type VARCHAR NOT NULL,
                original_node JSON,
                changed_node JSON NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (sandbox_id) REFERENCES sandboxes(id) ON DELETE CASCADE
            )
        """)
        await self.db.async_execute("""
            CREATE TABLE IF NOT EXISTS sandbox_edge_changes (
                id INTEGER PRIMARY KEY,
                sandbox_id INTEGER NOT NULL,
                edge_id INTEGER,
                change_type VARCHAR NOT NULL,
                original_edge JSON,
                changed_edge JSON NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (sandbox_id) REFERENCES sandboxes(id) ON DELETE CASCADE
            )
        """)

    async def count_nodes(self) -> int:
        """统计总节点数（由 Chroma 负责，此处返回 0 占位）"""
        return 0

    # ── Domain operations ──

    async def create_domain(self, domain: Domain) -> int:
        lastrowid = await self.db.async_save(
            """INSERT INTO domains (parent_id, domain_name, full_path, depth, season)
               VALUES (?, ?, ?, ?, ?) RETURNING id""",
            (domain.parent_id, domain.domain_name, domain.full_path, domain.depth, domain.season.value),
            return_lastrowid=True,
        )
        return int(lastrowid)

    async def get_domain_by_path(self, full_path: str) -> Optional[Domain]:
        row = await self.db.async_fetch_one("SELECT * FROM domains WHERE full_path = ?", (full_path,))
        return self._row_to_domain(row) if row else None

    async def get_domain(self, domain_id: int) -> Optional[Domain]:
        row = await self.db.async_fetch_one("SELECT * FROM domains WHERE id = ?", (domain_id,))
        return self._row_to_domain(row) if row else None

    async def list_child_domains(self, parent_id: Optional[int]) -> List[Domain]:
        if parent_id is None:
            rows = await self.db.async_fetch("SELECT * FROM domains WHERE parent_id IS NULL ORDER BY full_path")
        else:
            rows = await self.db.async_fetch("SELECT * FROM domains WHERE parent_id = ? ORDER BY full_path", (parent_id,))
        return [self._row_to_domain(r) for r in rows]

    async def update_domain_season(self, domain_id: int, season: Season) -> None:
        await self.db.async_save("UPDATE domains SET season = ? WHERE id = ?", (season.value, domain_id))

    @staticmethod
    def _row_to_domain(row: dict) -> Domain:
        return Domain(
            id=row["id"],
            parent_id=row["parent_id"],
            domain_name=row["domain_name"],
            full_path=row["full_path"],
            depth=row["depth"],
            season=Season(row["season"]),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )

    # ── Edge operations ──

    async def create_edge(self, edge: CognitiveEdge) -> int:
        """创建边，如果已存在(同一对节点同一类型)则更新强度"""
        try:
            lastrowid = await self.db.async_save(
                """INSERT INTO cog_edges (from_node_id, to_node_id, relation_type, strength, source)
                   VALUES (?, ?, ?, ?, ?) RETURNING id""",
                (edge.from_node_id, edge.to_node_id, edge.relation_type.value, edge.strength, edge.source),
                return_lastrowid=True,
            )
            return int(lastrowid)
        except Exception:
            await self.db.async_save(
                """UPDATE cog_edges SET strength = ?, source = ?
                   WHERE from_node_id = ? AND to_node_id = ? AND relation_type = ?""",
                (edge.strength, edge.source, edge.from_node_id, edge.to_node_id, edge.relation_type.value),
            )
            row = await self.db.async_fetch_one(
                """SELECT id FROM cog_edges
                   WHERE from_node_id = ? AND to_node_id = ? AND relation_type = ?""",
                (edge.from_node_id, edge.to_node_id, edge.relation_type.value),
            )
            return int(row["id"])

    async def get_edge(self, edge_id: int) -> Optional[CognitiveEdge]:
        row = await self.db.async_fetch_one("SELECT * FROM cog_edges WHERE id = ?", (edge_id,))
        return self._row_to_edge(row) if row else None

    async def get_edge_between(
        self, from_node: str, to_node: str, relation_type: RelationType
    ) -> Optional[CognitiveEdge]:
        row = await self.db.async_fetch_one(
            """SELECT * FROM cog_edges
               WHERE from_node_id = ? AND to_node_id = ? AND relation_type = ?""",
            (from_node, to_node, relation_type.value),
        )
        return self._row_to_edge(row) if row else None

    async def list_edges_from(self, node_id: str) -> List[CognitiveEdge]:
        rows = await self.db.async_fetch(
            "SELECT * FROM cog_edges WHERE from_node_id = ? ORDER BY strength DESC", (node_id,)
        )
        return [self._row_to_edge(r) for r in rows]

    async def list_edges_to(self, node_id: str) -> List[CognitiveEdge]:
        rows = await self.db.async_fetch(
            "SELECT * FROM cog_edges WHERE to_node_id = ? ORDER BY strength DESC", (node_id,)
        )
        return [self._row_to_edge(r) for r in rows]

    async def update_edge_strength(self, edge_id: int, strength: float) -> None:
        await self.db.async_save(
            "UPDATE cog_edges SET strength = ? WHERE id = ?",
            (max(0.0, min(1.0, strength)), edge_id),
        )

    @staticmethod
    def _row_to_edge(row: dict) -> CognitiveEdge:
        return CognitiveEdge(
            id=row["id"],
            from_node_id=row["from_node_id"],
            to_node_id=row["to_node_id"],
            relation_type=RelationType(row["relation_type"]),
            strength=float(row["strength"]),
            source=row.get("source"),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )

    # ── BFS expand ──

    async def bfs_expand(
        self, start_node_ids: List[str], max_depth: int = 2
    ) -> Set[str]:
        """从起点 BFS 扩展，收集关联节点 ID"""
        visited: Set[str] = set(start_node_ids)
        current: Set[str] = set(start_node_ids)

        for _ in range(max_depth):
            next_level: Set[str] = set()
            for node_id in current:
                edges = await self.list_edges_from(node_id)
                for edge in edges:
                    if edge.strength >= self.config.retrieval_strength_threshold and edge.to_node_id not in visited:
                        visited.add(edge.to_node_id)
                        next_level.add(edge.to_node_id)
            current = next_level
            if not current:
                break

        return visited

    # ── Change log ──

    async def log_change(self, log: ChangeLogEntry) -> int:
        lastrowid = await self.db.async_save(
            """INSERT INTO cog_change_log (node_id, edge_id, operation, old_values, new_values, reason, trace_id)
               VALUES (?, ?, ?, ?, ?, ?, ?) RETURNING id""",
            (
                log.node_id,
                log.edge_id,
                log.operation,
                json.dumps(log.old_values) if log.old_values else None,
                json.dumps(log.new_values) if log.new_values else None,
                log.reason,
                log.trace_id,
            ),
            return_lastrowid=True,
        )
        return int(lastrowid)


__all__ = ["YggdrasilStore"]