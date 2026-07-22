import logging
from typing import List, Optional, Set, Tuple, Dict

from src.core.config import YggdrasilConfig
from src.core.yggdrasil.models import (
    Domain,
    CognitiveNode,
    CognitiveEdge,
    SubtreeContext,
    Season,
)
from src.core.yggdrasil.store import YggdrasilStore
from src.core.yggdrasil.embedding import EmbeddingService

logger = logging.getLogger(__name__)


class SubtreeRetriever:
    """子树检索器 - ChromaDB 搜索 + DuckDB BFS 扩展"""

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
        max_nodes = max_nodes or self.config.retrieval_max_nodes
        max_depth = self.config.retrieval_max_depth
        threshold = self.config.retrieval_strength_threshold

        # 确定领域
        if domain_path is not None:
            domain = await self.store.get_domain_by_path(domain_path)
            if not domain:
                return SubtreeContext(
                    message=f"Domain {domain_path} not found",
                )
            chroma_filter = {
                "domain_path": {"$prefix": domain_path},
                "health": {"$gt": "0.0"},
            }
        else:
            domain = await self.store.get_domain_by_path("")
            chroma_filter = {"health": {"$gt": "0.0"}}

        # 1. ChromaDB 搜索 → 锚点
        anchor_results = await self.embedding.search(
            query_text=query,
            n_results=20,
            where=chroma_filter,
        )

        if not anchor_results:
            return SubtreeContext(
                domain=domain, message="No relevant nodes found",
            )

        anchor_nodes = [node for node, _ in anchor_results]

        # 2. BFS 沿边扩展
        anchor_ids = [str(n.id) for n in anchor_nodes]
        expanded_ids = await self.store.bfs_expand(anchor_ids, max_depth)
        expanded_ids = expanded_ids | set(anchor_ids)

        # 3. 收集节点
        all_nodes: List[CognitiveNode] = []
        for node_id in expanded_ids:
            node = await self.store.get_node(node_id)
            if node and node.health > 0.0 and node.strength >= threshold:
                all_nodes.append(node)

        if not all_nodes:
            all_nodes = anchor_nodes

        # 4. 排序：strength × (1 - distance) × season_weight
        anchor_scores: Dict[str, float] = {}
        for node, distance in anchor_results:
            anchor_scores[str(node.id)] = 1.0 - distance

        SEASON_BOOST = {Season.SUMMER: 1.2, Season.SPRING: 1.1, Season.AUTUMN: 1.0, Season.WINTER: 0.9}

        scored: List[Tuple[CognitiveNode, float]] = []
        for node in all_nodes:
            sim = anchor_scores.get(str(node.id), 0.5)
            boost = SEASON_BOOST.get(node.season, 1.0)
            score = node.strength * sim * boost
            scored.append((node, score))

        scored.sort(key=lambda x: x[1], reverse=True)

        # 5. 裁剪
        selected = scored[:max_nodes]
        selected_ids = {str(node.id) for node, _ in selected}
        selected_nodes = [node for node, _ in selected]

        # 收集边
        selected_edges = await self._collect_edges(selected_ids, threshold)

        # 估算 token
        total_text = "".join(f"{n.title} {n.content or ''}" for n in selected_nodes)
        estimated_tokens = int(len(total_text) / 4)

        # 更新最后访问时间
        for node in selected_nodes:
            await self.store.touch_node(str(node.id))

        return SubtreeContext(
            domain=domain,
            nodes=selected_nodes,
            edges=selected_edges,
            total_tokens=estimated_tokens,
        )

    async def _collect_edges(
        self, node_ids: Set[str], strength_threshold: float
    ) -> List[CognitiveEdge]:
        edges: List[CognitiveEdge] = []
        for node_id in node_ids:
            out_edges = await self.store.list_edges_from(node_id)
            for edge in out_edges:
                if edge.target_id in node_ids and edge.strength >= strength_threshold:
                    edges.append(edge)
        return edges


__all__ = ["SubtreeRetriever"]