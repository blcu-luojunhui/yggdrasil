import logging
from typing import List, Optional, Dict
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
from src.infra.database.mysql import AsyncMySQLPool

logger = logging.getLogger(__name__)

# 默认根领域
_DEFAULT_DOMAINS = [
    {"parent_id": None, "domain_name": "root", "full_path": "", "depth": 0},
]


class YggdrasilStore:
    """Yggdrasil 存储层 - 负责节点、边、领域的持久化"""

    def __init__(self, db: AsyncMySQLPool, config: YggdrasilConfig):
        self.db = db
        self.config = config

    async def ensure_skeleton(self) -> None:
        """确保基础骨架存在，创建根领域"""
        # 检查表是否存在，创建默认根领域
        existing = await self.db.async_fetch_one("SELECT id FROM domains WHERE full_path = ''")
        if not existing:
            await self.db.async_save(
                """
                INSERT INTO domains (parent_id, domain_name, full_path, depth, season)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (None, "root", "", 0, Season.SPRING.value),
            )
            logger.info("Yggdrasil root domain created")

    async def count_nodes(self) -> int:
        """统计总节点数"""
        row = await self.db.async_fetch_one("SELECT COUNT(*) as cnt FROM cog_nodes WHERE is_isolated = FALSE")
        return row["cnt"] if row else 0

    # ---------- Domain operations ----------

    async def create_domain(self, domain: Domain) -> int:
        """创建领域"""
        lastrowid = await self.db.async_save(
            """
            INSERT INTO domains (parent_id, domain_name, full_path, depth, season)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                domain.parent_id,
                domain.domain_name,
                domain.full_path,
                domain.depth,
                domain.season.value,
            ),
            return_lastrowid=True,
        )
        return int(lastrowid)

    async def get_domain_by_path(self, full_path: str) -> Optional[Domain]:
        """按路径获取领域"""
        row = await self.db.async_fetch_one(
            "SELECT * FROM domains WHERE full_path = %s", (full_path,)
        )
        if not row:
            return None
        return self._row_to_domain(row)

    async def get_domain(self, domain_id: int) -> Optional[Domain]:
        """按 ID 获取领域"""
        row = await self.db.async_fetch_one(
            "SELECT * FROM domains WHERE id = %s", (domain_id,)
        )
        if not row:
            return None
        return self._row_to_domain(row)

    async def list_child_domains(self, parent_id: Optional[int]) -> List[Domain]:
        """列出子领域"""
        if parent_id is None:
            rows = await self.db.async_fetch(
                "SELECT * FROM domains WHERE parent_id IS NULL ORDER BY full_path"
            )
        else:
            rows = await self.db.async_fetch(
                "SELECT * FROM domains WHERE parent_id = %s ORDER BY full_path",
                (parent_id,)
            )
        return [self._row_to_domain(r) for r in rows]

    async def update_domain_season(self, domain_id: int, season: Season) -> None:
        """更新领域季节"""
        await self.db.async_save(
            "UPDATE domains SET season = %s WHERE id = %s",
            (season.value, domain_id),
        )

    def _row_to_domain(self, row: dict) -> Domain:
        return Domain(
            id=row["id"],
            parent_id=row["parent_id"],
            domain_name=row["domain_name"],
            full_path=row["full_path"],
            depth=row["depth"],
            season=Season(row["season"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    # ---------- Node operations ----------

    async def create_node(self, node: CognitiveNode) -> int:
        """创建认知节点"""
        lastrowid = await self.db.async_save(
            """
            INSERT INTO cog_nodes (
                domain_id, role, node_name, description, content, embedding,
                strength, health, is_isolated, last_used_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                node.domain_id,
                node.role.value,
                node.node_name,
                node.description,
                node.content,
                node.embedding,
                node.strength,
                node.health,
                node.is_isolated,
                node.last_used_at,
            ),
            return_lastrowid=True,
        )
        return int(lastrowid)

    async def get_node(self, node_id: int) -> Optional[CognitiveNode]:
        """获取节点"""
        row = await self.db.async_fetch_one(
            "SELECT * FROM cog_nodes WHERE id = %s", (node_id,)
        )
        if not row:
            return None
        return self._row_to_node(row)

    async def list_nodes_by_domain(
        self, domain_id: int, include_isolated: bool = False
    ) -> List[CognitiveNode]:
        """列出领域下所有节点"""
        if include_isolated:
            rows = await self.db.async_fetch(
                "SELECT * FROM cog_nodes WHERE domain_id = %s ORDER BY strength DESC",
                (domain_id,)
            )
        else:
            rows = await self.db.async_fetch(
                "SELECT * FROM cog_nodes WHERE domain_id = %s AND is_isolated = FALSE ORDER BY strength DESC",
                (domain_id,)
            )
        return [self._row_to_node(r) for r in rows]

    async def update_node_strength(self, node_id: int, strength: float) -> None:
        """更新节点强度"""
        await self.db.async_save(
            "UPDATE cog_nodes SET strength = %s, last_used_at = NOW() WHERE id = %s",
            (max(0.0, min(1.0, strength)), node_id),
        )

    async def update_node_health(self, node_id: int, health: float) -> None:
        """更新节点健康度"""
        await self.db.async_save(
            "UPDATE cog_nodes SET health = %s WHERE id = %s",
            (max(0.0, min(1.0, health)), node_id),
        )

    async def isolate_node(self, node_id: int, isolated: bool) -> None:
        """隔离或恢复节点"""
        await self.db.async_save(
            "UPDATE cog_nodes SET is_isolated = %s WHERE id = %s",
            (isolated, node_id),
        )

    async def search_nodes_by_embedding(
        self, embedding: bytes, limit: int = 10
    ) -> List[CognitiveNode]:
        """
        基于嵌入向量搜索最相似节点。
        Phase 1: 简单余弦相似度计算，不使用专用 ANN 库。
        """
        # 这里简单实现，取出所有非隔离节点计算相似度
        # 生产环境应使用专用向量库如 pgvector/chroma
        all_nodes = await self.db.async_fetch(
            "SELECT * FROM cog_nodes WHERE is_isolated = FALSE AND embedding IS NOT NULL"
        )
        # TODO: 实现余弦相似度搜索
        # 对于 Phase 1，先返回结果占位
        results = []
        for row in all_nodes[:limit]:
            results.append(self._row_to_node(row))
        return results

    async def count_nodes_by_role(self) -> Dict[CognitiveRole, int]:
        """按 role 统计节点数"""
        rows = await self.db.async_fetch(
            "SELECT role, COUNT(*) as cnt FROM cog_nodes WHERE is_isolated = FALSE GROUP BY role"
        )
        return {CognitiveRole(r["role"]): r["cnt"] for r in rows}

    def _row_to_node(self, row: dict) -> CognitiveNode:
        return CognitiveNode(
            id=row["id"],
            domain_id=row["domain_id"],
            role=CognitiveRole(row["role"]),
            node_name=row["node_name"],
            description=row["description"],
            content=row["content"],
            embedding=row["embedding"],
            strength=float(row["strength"]),
            health=float(row["health"]),
            is_isolated=bool(row["is_isolated"]),
            last_used_at=row["last_used_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    # ---------- Edge operations ----------

    async def create_edge(self, edge: CognitiveEdge) -> int:
        """创建边"""
        try:
            lastrowid = await self.db.async_save(
                """
                INSERT INTO cog_edges (from_node_id, to_node_id, relation_type, strength, source)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    edge.from_node_id,
                    edge.to_node_id,
                    edge.relation_type.value,
                    edge.strength,
                    edge.source,
                ),
                return_lastrowid=True,
            )
            return int(lastrowid)
        except Exception:
            # 唯一键冲突，说明已存在，更新强度
            await self.db.async_save(
                """
                UPDATE cog_edges SET strength = %s, source = %s
                WHERE from_node_id = %s AND to_node_id = %s AND relation_type = %s
                """,
                (
                    edge.strength,
                    edge.source,
                    edge.from_node_id,
                    edge.to_node_id,
                    edge.relation_type.value,
                ),
            )
            row = await self.db.async_fetch_one(
                """
                SELECT id FROM cog_edges
                WHERE from_node_id = %s AND to_node_id = %s AND relation_type = %s
                """,
                (edge.from_node_id, edge.to_node_id, edge.relation_type.value),
            )
            return row["id"]

    async def get_edge(self, edge_id: int) -> Optional[CognitiveEdge]:
        """获取边"""
        row = await self.db.async_fetch_one(
            "SELECT * FROM cog_edges WHERE id = %s", (edge_id,)
        )
        if not row:
            return None
        return self._row_to_edge(row)

    async def get_edge_between(
        self, from_node: int, to: int, relation_type: RelationType
    ) -> Optional[CognitiveEdge]:
        """获取两节点之间指定类型的边"""
        row = await self.db.async_fetch_one(
            """
            SELECT * FROM cog_edges
            WHERE from_node_id = %s AND to_node_id = %s AND relation_type = %s
            """,
            (from_node, to, relation_type.value),
        )
        if not row:
            return None
        return self._row_to_edge(row)

    async def list_edges_from(self, node_id: int) -> List[CognitiveEdge]:
        """列出从该节点出发的所有边"""
        rows = await self.db.async_fetch(
            "SELECT * FROM cog_edges WHERE from_node_id = %s ORDER BY strength DESC",
            (node_id,)
        )
        return [self._row_to_edge(r) for r in rows]

    async def list_edges_to(self, node_id: int) -> List[CognitiveEdge]:
        """列出指向该节点的所有边"""
        rows = await self.db.async_fetch(
            "SELECT * FROM cog_edges WHERE to_node_id = %s ORDER BY strength DESC",
            (node_id,)
        )
        return [self._row_to_edge(r) for r in rows]

    async def update_edge_strength(self, edge_id: int, strength: float) -> None:
        """更新边强度"""
        await self.db.async_save(
            "UPDATE cog_edges SET strength = %s WHERE id = %s",
            (max(0.0, min(1.0, strength)), edge_id),
        )

    def _row_to_edge(self, row: dict) -> CognitiveEdge:
        return CognitiveEdge(
            id=row["id"],
            from_node_id=row["from_node_id"],
            to_node_id=row["to_node_id"],
            relation_type=RelationType(row["relation_type"]),
            strength=float(row["strength"]),
            source=row["source"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    # ---------- BFS 扩展 ----------

    async def bfs_expand(
        self, start_node_ids: List[int], max_depth: int = 2
    ) -> List[CognitiveNode]:
        """从起点开始 BFS 扩展，收集关联节点"""
        visited = set(start_node_ids)
        current = set(start_node_ids)
        for _ in range(max_depth):
            next_level = set()
            for node_id in current:
                edges = await self.list_edges_from(node_id)
                for edge in edges:
                    if edge.strength >= self.config.retrieval_strength_threshold and not edge.to_node_id in visited:
                        visited.add(edge.to_node_id)
                        next_level.add(edge.to_node_id)
            current = next_level
            if not current:
                break

        # 获取所有访问过的节点
        nodes = []
        for node_id in visited:
            node = await self.get_node(node_id)
            if node and not node.is_isolated:
                nodes.append(node)
        return nodes

    # ---------- Change log ----------

    async def log_change(self, log: ChangeLogEntry) -> int:
        """记录变更日志"""
        lastrowid = await self.db.async_save(
            """
            INSERT INTO cog_change_log (node_id, edge_id, operation, old_values, new_values, reason, trace_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                log.node_id,
                log.edge_id,
                log.operation,
                log.old_values,
                log.new_values,
                log.reason,
                log.trace_id,
            ),
            return_lastrowid=True,
        )
        return int(lastrowid)


__all__ = ["YggdrasilStore"]
