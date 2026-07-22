import json
import logging
import uuid
import time
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
    TreeLogEntry,
)
from src.infra.database.duckdb import DuckDBPool

logger = logging.getLogger(__name__)


def _uuid_v7() -> str:
    """生成 UUID v7（时间有序）"""
    ts = int(time.time() * 1000)
    u = uuid.uuid4()
    return f"{u.hex[:8]}-{u.hex[8:12]}-7{u.hex[13:16]}-{u.hex[16:20]}-{u.hex[20:]}"


class YggdrasilStore:
    """Yggdrasil 存储层 - DuckDB 持久化领域、边、变更日志、沙盒"""

    def __init__(self, db: DuckDBPool, config: YggdrasilConfig):
        self.db = db
        self.config = config

    async def ensure_skeleton(self) -> None:
        await self._create_tables()

        existing = await self.db.async_fetch_one("SELECT id FROM domains WHERE full_path = ''")
        if not existing:
            await self.db.async_save(
                "INSERT INTO domains (parent_id, domain_name, full_path, depth) VALUES (NULL, 'root', '', 0)"
            )
            logger.info("Yggdrasil root domain created")

    async def _create_tables(self):
        await self.db.async_execute("""
            CREATE TABLE IF NOT EXISTS domains (
                id INTEGER PRIMARY KEY,
                parent_id INTEGER,
                domain_name VARCHAR NOT NULL,
                full_path VARCHAR NOT NULL UNIQUE,
                depth INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (parent_id) REFERENCES domains(id) ON DELETE CASCADE
            )
        """)
        await self.db.async_execute("""
            CREATE TABLE IF NOT EXISTS cog_node (
                id CHAR(36) PRIMARY KEY,
                role VARCHAR NOT NULL,
                domain_id INTEGER NOT NULL,
                domain_path VARCHAR(1024) NOT NULL,
                title VARCHAR(255) NOT NULL,
                content TEXT,
                strength DOUBLE DEFAULT 0.5,
                health DOUBLE DEFAULT 1.0,
                season VARCHAR DEFAULT 'spring',
                embedding_id VARCHAR(255),
                tenant_id VARCHAR(64) DEFAULT 'default',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_accessed_at TIMESTAMP
            )
        """)
        await self.db.async_execute("""
            CREATE TABLE IF NOT EXISTS cog_edge (
                id CHAR(36) PRIMARY KEY,
                source_id CHAR(36) NOT NULL,
                target_id CHAR(36) NOT NULL,
                relation VARCHAR NOT NULL,
                strength DOUBLE DEFAULT 0.5,
                evidence_count INT DEFAULT 1,
                last_activated TIMESTAMP,
                source_origin VARCHAR(255),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(source_id, target_id, relation),
                FOREIGN KEY (source_id) REFERENCES cog_node(id) ON DELETE CASCADE,
                FOREIGN KEY (target_id) REFERENCES cog_node(id) ON DELETE CASCADE
            )
        """)
        await self.db.async_execute("""
            CREATE TABLE IF NOT EXISTS tree_log (
                id INTEGER PRIMARY KEY,
                operation VARCHAR(50) NOT NULL,
                entity_type VARCHAR(20) NOT NULL,
                entity_id CHAR(36) NOT NULL,
                changes JSON,
                operator VARCHAR(255),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await self.db.async_execute("""
            CREATE TABLE IF NOT EXISTS season_cycle (
                id INTEGER PRIMARY KEY,
                domain_path VARCHAR(1024) DEFAULT '/',
                current_season VARCHAR DEFAULT 'spring',
                cycle_anchor TIMESTAMP,
                cycle_duration_hours INT DEFAULT 168,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Phase 3-4 扩展表（预留）
        await self.db.async_execute("""
            CREATE TABLE IF NOT EXISTS branch (
                id CHAR(36) PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                parent_branch_id CHAR(36),
                status VARCHAR DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by VARCHAR(255),
                FOREIGN KEY (parent_branch_id) REFERENCES branch(id)
            )
        """)
        await self.db.async_execute("""
            CREATE TABLE IF NOT EXISTS cooccurrence (
                node_a_id CHAR(36) NOT NULL,
                node_b_id CHAR(36) NOT NULL,
                count INT DEFAULT 0,
                last_cooccur TIMESTAMP,
                PRIMARY KEY (node_a_id, node_b_id)
            )
        """)
        logger.info("Yggdrasil tables created")

    # ── Domain operations ──

    async def create_domain(self, domain: Domain) -> int:
        lastrowid = await self.db.async_save(
            "INSERT INTO domains (parent_id, domain_name, full_path, depth) VALUES (?, ?, ?, ?) RETURNING id",
            (domain.parent_id, domain.domain_name, domain.full_path, domain.depth),
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

    @staticmethod
    def _row_to_domain(row: dict) -> Domain:
        return Domain(
            id=row["id"],
            parent_id=row.get("parent_id"),
            domain_name=row["domain_name"],
            full_path=row["full_path"],
            depth=row["depth"],
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )

    # ── Node operations ──

    async def create_node(self, node: CognitiveNode) -> str:
        node.id = node.id or _uuid_v7()
        await self.db.async_save(
            """INSERT INTO cog_node (id, role, domain_id, domain_path, title, content,
               strength, health, season, embedding_id, tenant_id, last_accessed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                node.id, node.role.value, node.domain_id, node.domain_path,
                node.title, node.content, node.strength, node.health,
                node.season.value, node.embedding_id, node.tenant_id,
                node.last_accessed_at,
            ),
        )
        return node.id

    async def get_node(self, node_id: str) -> Optional[CognitiveNode]:
        row = await self.db.async_fetch_one("SELECT * FROM cog_node WHERE id = ?", (node_id,))
        return self._row_to_node(row) if row else None

    async def update_node_strength(self, node_id: str, strength: float) -> None:
        await self.db.async_save(
            "UPDATE cog_node SET strength = ? WHERE id = ?",
            (max(0.0, min(1.0, strength)), node_id),
        )

    async def update_node_health(self, node_id: str, health: float) -> None:
        await self.db.async_save(
            "UPDATE cog_node SET health = ? WHERE id = ?",
            (max(0.0, min(1.0, health)), node_id),
        )

    async def update_node_season(self, node_id: str, season: Season) -> None:
        await self.db.async_save(
            "UPDATE cog_node SET season = ? WHERE id = ?",
            (season.value, node_id),
        )

    async def touch_node(self, node_id: str) -> None:
        await self.db.async_save(
            "UPDATE cog_node SET last_accessed_at = CURRENT_TIMESTAMP WHERE id = ?",
            (node_id,),
        )

    async def list_nodes(
        self, domain_id: Optional[int] = None, min_health: float = 0.0
    ) -> List[CognitiveNode]:
        if domain_id is not None:
            rows = await self.db.async_fetch(
                "SELECT * FROM cog_node WHERE domain_id = ? AND health > ? ORDER BY strength DESC",
                (domain_id, min_health),
            )
        else:
            rows = await self.db.async_fetch(
                "SELECT * FROM cog_node WHERE health > ? ORDER BY strength DESC",
                (min_health,),
            )
        return [self._row_to_node(r) for r in rows]

    async def list_nodes_by_domain_path(
        self, domain_path: str, min_health: float = 0.0
    ) -> List[CognitiveNode]:
        # 物化路径前缀匹配
        rows = await self.db.async_fetch(
            "SELECT * FROM cog_node WHERE domain_path LIKE ? AND health > ? ORDER BY strength DESC",
            (f"{domain_path}%", min_health),
        )
        return [self._row_to_node(r) for r in rows]

    async def count_nodes(self) -> int:
        row = await self.db.async_fetch_one("SELECT COUNT(*) as cnt FROM cog_node")
        return row["cnt"] if row else 0

    async def count_nodes_by_role(self) -> Dict[CognitiveRole, int]:
        rows = await self.db.async_fetch("SELECT role, COUNT(*) as cnt FROM cog_node GROUP BY role")
        return {CognitiveRole(r["role"]): r["cnt"] for r in rows}

    @staticmethod
    def _row_to_node(row: dict) -> CognitiveNode:
        return CognitiveNode(
            id=row["id"],
            role=CognitiveRole(row["role"]),
            domain_id=row["domain_id"],
            domain_path=row.get("domain_path", ""),
            title=row["title"],
            content=row.get("content"),
            strength=float(row["strength"]),
            health=float(row["health"]),
            season=Season(row.get("season", "spring")),
            embedding_id=row.get("embedding_id"),
            tenant_id=row.get("tenant_id", "default"),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
            last_accessed_at=row.get("last_accessed_at"),
        )

    # ── Edge operations ──

    async def create_edge(self, edge: CognitiveEdge) -> str:
        edge.id = edge.id or _uuid_v7()
        try:
            await self.db.async_save(
                """INSERT INTO cog_edge (id, source_id, target_id, relation,
                   strength, evidence_count, last_activated, source_origin)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    edge.id, edge.source_id, edge.target_id, edge.relation.value,
                    edge.strength, edge.evidence_count,
                    edge.last_activated, edge.source_origin,
                ),
            )
            return edge.id
        except Exception:
            # 唯一键冲突，更新
            await self.db.async_save(
                """UPDATE cog_edge SET strength = ?, evidence_count = evidence_count + 1,
                   last_activated = ?, source_origin = ?
                   WHERE source_id = ? AND target_id = ? AND relation = ?""",
                (
                    edge.strength, edge.last_activated, edge.source_origin,
                    edge.source_id, edge.target_id, edge.relation.value,
                ),
            )
            row = await self.db.async_fetch_one(
                "SELECT id FROM cog_edge WHERE source_id = ? AND target_id = ? AND relation = ?",
                (edge.source_id, edge.target_id, edge.relation.value),
            )
            return str(row["id"])

    async def get_edge(self, edge_id: str) -> Optional[CognitiveEdge]:
        row = await self.db.async_fetch_one("SELECT * FROM cog_edge WHERE id = ?", (edge_id,))
        return self._row_to_edge(row) if row else None

    async def get_edge_between(
        self, source_id: str, target_id: str, relation: RelationType
    ) -> Optional[CognitiveEdge]:
        row = await self.db.async_fetch_one(
            "SELECT * FROM cog_edge WHERE source_id = ? AND target_id = ? AND relation = ?",
            (source_id, target_id, relation.value),
        )
        return self._row_to_edge(row) if row else None

    async def list_edges_from(self, node_id: str) -> List[CognitiveEdge]:
        rows = await self.db.async_fetch(
            "SELECT * FROM cog_edge WHERE source_id = ? ORDER BY strength DESC", (node_id,)
        )
        return [self._row_to_edge(r) for r in rows]

    async def list_edges_to(self, node_id: str) -> List[CognitiveEdge]:
        rows = await self.db.async_fetch(
            "SELECT * FROM cog_edge WHERE target_id = ? ORDER BY strength DESC", (node_id,)
        )
        return [self._row_to_edge(r) for r in rows]

    async def update_edge_strength(self, edge_id: str, strength: float) -> None:
        await self.db.async_save(
            "UPDATE cog_edge SET strength = ? WHERE id = ?",
            (max(0.0, min(1.0, strength)), edge_id),
        )

    async def activate_edge(self, edge_id: str) -> None:
        await self.db.async_save(
            "UPDATE cog_edge SET last_activated = CURRENT_TIMESTAMP, evidence_count = evidence_count + 1 WHERE id = ?",
            (edge_id,),
        )

    @staticmethod
    def _row_to_edge(row: dict) -> CognitiveEdge:
        return CognitiveEdge(
            id=row["id"],
            source_id=row["source_id"],
            target_id=row["target_id"],
            relation=RelationType(row["relation"]),
            strength=float(row["strength"]),
            evidence_count=row.get("evidence_count", 1),
            last_activated=row.get("last_activated"),
            source_origin=row.get("source_origin"),
            created_at=row.get("created_at"),
        )

    # ── BFS expand ──

    async def bfs_expand(self, start_node_ids: List[str], max_depth: int = 2) -> Set[str]:
        visited: Set[str] = set(start_node_ids)
        current: Set[str] = set(start_node_ids)

        for _ in range(max_depth):
            next_level: Set[str] = set()
            for node_id in current:
                edges = await self.list_edges_from(node_id)
                for edge in edges:
                    if edge.strength >= self.config.retrieval_strength_threshold and edge.target_id not in visited:
                        visited.add(edge.target_id)
                        next_level.add(edge.target_id)
            current = next_level
            if not current:
                break

        return visited

    # ── Tree log ──

    async def log_change(self, log: TreeLogEntry) -> int:
        lastrowid = await self.db.async_save(
            """INSERT INTO tree_log (operation, entity_type, entity_id, changes, operator)
               VALUES (?, ?, ?, ?, ?) RETURNING id""",
            (log.operation, log.entity_type, log.entity_id,
             json.dumps(log.changes) if log.changes else None, log.operator),
            return_lastrowid=True,
        )
        return int(lastrowid)

    # ── Season cycle ──

    async def get_season_cycle(self, domain_path: str = "/") -> Optional[dict]:
        return await self.db.async_fetch_one(
            "SELECT * FROM season_cycle WHERE domain_path = ?", (domain_path,)
        )

    async def upsert_season_cycle(self, domain_path: str, season: Season, cycle_duration_hours: int = 168):
        existing = await self.get_season_cycle(domain_path)
        if existing:
            await self.db.async_save(
                "UPDATE season_cycle SET current_season = ?, cycle_duration_hours = ?, updated_at = CURRENT_TIMESTAMP WHERE domain_path = ?",
                (season.value, cycle_duration_hours, domain_path),
            )
        else:
            await self.db.async_save(
                "INSERT INTO season_cycle (domain_path, current_season, cycle_anchor, cycle_duration_hours) VALUES (?, ?, CURRENT_TIMESTAMP, ?)",
                (domain_path, season.value, cycle_duration_hours),
            )


__all__ = ["YggdrasilStore", "_uuid_v7"]