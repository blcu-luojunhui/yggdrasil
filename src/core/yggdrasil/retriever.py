import logging
from typing import List, Tuple, Set
import numpy as np

from src.core.config import YggdrasilConfig
from src.core.yggdrasil.models import (
    Domain,
    CognitiveNode,
    CognitiveEdge,
    SubtreeContext,
)
from src.core.yggdrasil.store import YggdrasilStore
from src.core.yggdrasil.embedding import EmbeddingService

logger = logging.getLogger(__name__)


class SubtreeRetriever:
    """子树检索器 - 根据意图检索相关认知子图"""

    def __init__(
        self,
        store: YggdrasilStore,
        embedding: EmbeddingService,
        config: YggdrasilConfig,
    ):
        self.store = store
        self.embedding = embedding
        self.config = config

    async def retrieve(
        self,
        query: str,
        domain_path: Optional[str] = None,
        max_nodes: Optional[int] = None,
    ) -> SubtreeContext:
        """
        检索认知子树：

        1. 种子定位：query 嵌入 → ANN 搜索 → 锚点节点
        2. 子图扩展：沿正向边 BFS 扩展
        3. 排序修剪：按 strength × 相似度排序，截取到预算
        4. 序列化：输出结构化上下文
        """
        max_nodes = max_nodes or self.config.retrieval_max_nodes
        max_depth = self.config.retrieval_max_depth
        threshold = self.config.retrieval_strength_threshold

        # 1. 生成 query 嵌入
        query_emb = await self.embedding.embed_text(query)

        # 2. 种子定位：找到 top-k 相似节点作为锚点
        # Phase 1: 简单暴力搜索，后续可优化为 ANN
        if domain_path is not None:
            domain = await self.store.get_domain_by_path(domain_path)
            if not domain:
                return SubtreeContext(
                    domain=Domain(parent_id=None, domain_name="empty", full_path=domain_path, depth=0),
                    nodes=[],
                    edges=[],
                    total_tokens=0,
                    message=f"Domain {domain_path} not found",
                )
            nodes = await self.store.list_nodes_by_domain(domain.id, include_isolated=False)
        else:
            # 获取所有非隔离节点
            # FIXME: 这只是 Phase 1 做法，生产环境需要索引
            rows = await self.store.db.async_fetch(
                "SELECT id, embedding FROM cog_nodes WHERE is_isolated = FALSE AND embedding IS NOT NULL"
            )
            nodes = []
            candidates = []
            for row in rows:
                candidates.append((row["id"], row["embedding"]))

            # 相似度搜索
            similar = self.embedding.similarity_search(query_emb, candidates, top_k=20)
            nodes = []
            for node_id, _ in similar:
                node = await self.store.get_node(node_id)
                if node:
                    nodes.append(node)
            domain = await self.store.get_domain_by_path("")
            if not domain:
                domain = Domain(parent_id=None, domain_name="root", full_path="", depth=0)

        if not nodes:
            return SubtreeContext(
                domain=domain,
                nodes=[],
                edges=[],
                total_tokens=0,
                message="No relevant nodes found",
            )

        # 按相似度排序，取 top 锚点
        if "similar" in locals():
            # already sorted
            pass
        else:
            # 对 domain 内节点重新计算相似度
            candidates = [(n.id, n.embedding) for n in nodes if n.embedding is not None]
            similar = self.embedding.similarity_search(query_emb, candidates, top_k=min(10, len(candidates)))
            anchor_ids = [node_id for node_id, _ in similar]
            nodes = [await self.store.get_node(node_id) for node_id in anchor_ids]
            nodes = [n for n in nodes if n is not None]

        # 3. BFS 扩展
        anchor_ids = [n.id for n in nodes]
        expanded_nodes = await self._bfs_expand(anchor_ids, max_depth, threshold)

        # 获取所有扩展节点
        all_nodes: List[CognitiveNode] = []
        visited_ids: Set[int] = set()
        for node_id in expanded_nodes:
            if node_id not in visited_ids:
                node = await self.store.get_node(node_id)
                if node and not node.is_isolated:
                    all_nodes.append(node)
                    visited_ids.add(node_id)

        # 4. 排序：strength × 语义相似度
        scored = await self._score_nodes(all_nodes, query_emb)
        scored.sort(key=lambda x: x[1], reverse=True)

        # 截取到 max_nodes
        selected = scored[:max_nodes]
        selected_ids = {node.id for node, _ in selected}
        selected_nodes = [node for node, _ in selected]

        # 收集选中节点之间的边
        selected_edges = await self._collect_edges(selected_ids, threshold)

        # 5. 估算 token 数（粗略估算：每个字符 ≈ 0.25 token）
        total_text = "".join(
            f"{n.node_name} {n.description or ''} {n.content or ''}" for n in selected_nodes
        )
        estimated_tokens = int(len(total_text) / 4)

        return SubtreeContext(
            domain=domain,
            nodes=selected_nodes,
            edges=selected_edges,
            total_tokens=estimated_tokens,
        )

    async def _bfs_expand(
        self, start_ids: List[int], max_depth: int, strength_threshold: float
    ) -> Set[int]:
        """BFS 扩展，收集所有可达节点"""
        visited: Set[int] = set(start_ids)
        current = set(start_ids)

        for depth in range(max_depth):
            next_level: Set[int] = set()
            for node_id in current:
                edges = await self.store.list_edges_from(node_id)
                for edge in edges:
                    if edge.strength >= strength_threshold and edge.to_node_id not in visited:
                        visited.add(edge.to_node_id)
                        next_level.add(edge.to_node_id)
            current = next_level
            if not current:
                break

        return visited

    async def _score_nodes(
        self, nodes: List[CognitiveNode], query_emb: np.ndarray
    ) -> List[Tuple[CognitiveNode, float]]:
        """给节点打分：strength × 语义相似度"""
        scored: List[Tuple[CognitiveNode, float]] = []
        for node in nodes:
            if node.embedding is None:
                # 没有嵌入，只靠 strength
                score = node.strength * 0.5
            else:
                embedding = self.embedding.deserialize(node.embedding)
                similarity = self.embedding.cosine_similarity(query_emb, embedding)
                score = node.strength * similarity
            scored.append((node, score))
        return scored

    async def _collect_edges(self, node_ids: Set[int], strength_threshold: float) -> List[CognitiveEdge]:
        """收集节点之间的边"""
        edges: List[CognitiveEdge] = []
        for node_id in node_ids:
            out_edges = await self.store.list_edges_from(node_id)
            for edge in out_edges:
                if edge.to_node_id in node_ids and edge.strength >= strength_threshold:
                    edges.append(edge)
        return edges


__all__ = ["SubtreeRetriever"]
