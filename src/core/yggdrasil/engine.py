import logging
from typing import Optional, List
from datetime import datetime

from src.core.config import YggdrasilConfig
from src.core.yggdrasil.models import (
    Domain,
    CognitiveNode,
    CognitiveEdge,
    CognitiveRole,
    RelationType,
    SubtreeContext,
    TreeLogEntry,
)
from src.core.yggdrasil.store import YggdrasilStore, _uuid_v7
from src.core.yggdrasil.retriever import SubtreeRetriever
from src.core.yggdrasil.embedding import EmbeddingService
from src.infra.observability import MetricsCollector

logger = logging.getLogger(__name__)


class YggdrasilEngine:
    """Yggdrasil 世界树引擎 - 统一 API，整合 ChromaDB + DuckDB"""

    def __init__(
        self,
        store: YggdrasilStore,
        retriever: SubtreeRetriever,
        embedding: EmbeddingService,
        metrics: MetricsCollector,
    ):
        self.store = store
        self.retriever = retriever
        self.embedding = embedding
        self.metrics = metrics

    # ── Retrieve ──

    async def retrieve(
        self, query: str, domain_path: Optional[str] = None, max_nodes: Optional[int] = None
    ) -> SubtreeContext:
        self.metrics.increment_retrieval()
        context = await self.retriever.retrieve(query, domain_path, max_nodes)
        self.metrics.observe_retrieval_nodes(len(context.nodes))
        return context

    async def get_markdown_context(self, query: str, domain_path: Optional[str] = None) -> str:
        context = await self.retrieve(query, domain_path)
        return context.to_markdown()

    # ── Domain ──

    async def create_domain(self, domain_name: str, parent_path: Optional[str] = None) -> Domain:
        if parent_path is None:
            root = await self.store.get_domain_by_path("")
            if not root:
                raise RuntimeError("Root domain not found, call ensure_skeleton first")
            full_path = domain_name
            depth = 1
            parent_id = root.id
        else:
            parent = await self.store.get_domain_by_path(parent_path)
            if not parent:
                raise ValueError(f"Parent domain {parent_path} not found")
            full_path = f"{parent_path}/{domain_name}".strip("/")
            depth = parent.depth + 1
            parent_id = parent.id

        existing = await self.store.get_domain_by_path(full_path)
        if existing:
            return existing

        domain = Domain(parent_id=parent_id, domain_name=domain_name, full_path=full_path, depth=depth)
        domain.id = await self.store.create_domain(domain)
        return domain

    # ── Node ──

    async def create_node(
        self,
        domain_path: str,
        role: CognitiveRole,
        title: str,
        content: Optional[str] = None,
    ) -> CognitiveNode:
        domain = await self.store.get_domain_by_path(domain_path)
        if not domain:
            raise ValueError(f"Domain {domain_path} not found")

        node = CognitiveNode(
            id=_uuid_v7(),
            role=role,
            domain_id=domain.id,
            domain_path=domain_path,
            title=title,
            content=content,
        )
        node.id = await self.store.create_node(node)
        await self.embedding.upsert_node(node)
        self.metrics.increment_node_created(role.value)
        return node

    async def get_node(self, node_id: str) -> Optional[CognitiveNode]:
        return await self.store.get_node(node_id)

    async def list_nodes(self, domain_path: str) -> List[CognitiveNode]:
        domain = await self.store.get_domain_by_path(domain_path)
        if not domain:
            return []
        return await self.store.list_nodes(domain_id=domain.id, min_health=0.0)

    # ── Edge ──

    async def add_edge(
        self,
        source_id: str,
        target_id: str,
        relation: RelationType,
        strength: float = 0.5,
        source_origin: Optional[str] = None,
    ) -> str:
        edge = CognitiveEdge(
            source_id=source_id,
            target_id=target_id,
            relation=relation,
            strength=strength,
            source_origin=source_origin,
        )
        edge.id = await self.store.create_edge(edge)
        self.metrics.increment_edge_updated(relation.value)
        return edge.id

    # ── Feedback ──

    async def feedback(
        self,
        node_id: Optional[str] = None,
        edge_id: Optional[str] = None,
        success: bool = True,
        step: float = 0.1,
        trace_id: Optional[str] = None,
    ) -> None:
        if node_id:
            node = await self.store.get_node(node_id)
            if node:
                delta = step if success else -step
                new_strength = max(0.0, min(1.0, node.strength + delta))
                await self.store.update_node_strength(node_id, new_strength)
                await self.store.touch_node(node_id)

                await self.store.log_change(TreeLogEntry(
                    operation="update_node",
                    entity_type="node",
                    entity_id=node_id,
                    changes={"strength": {"old": node.strength, "new": new_strength}},
                    operator=trace_id,
                ))

        if edge_id:
            edge = await self.store.get_edge(edge_id)
            if edge:
                delta = step if success else -step
                new_strength = max(0.0, min(1.0, edge.strength + delta))
                await self.store.update_edge_strength(edge_id, new_strength)
                if success:
                    await self.store.activate_edge(edge_id)

                await self.store.log_change(TreeLogEntry(
                    operation="update_edge",
                    entity_type="edge",
                    entity_id=edge_id,
                    changes={"strength": {"old": edge.strength, "new": new_strength}},
                    operator=trace_id,
                ))

    async def strengthen(
        self, source_id: str, target_id: str, relation: RelationType,
        step: float = 0.1, source_origin: str = "execution", trace_id: Optional[str] = None,
    ) -> None:
        edge = await self.store.get_edge_between(source_id, target_id, relation)
        if edge:
            new_strength = min(1.0, edge.strength + step)
            await self.store.update_edge_strength(edge.id, new_strength)
            await self.store.activate_edge(edge.id)
        else:
            await self.add_edge(source_id, target_id, relation, strength=0.5 + step, source_origin=source_origin)

    # ── Lifecycle ──

    async def ensure_skeleton(self) -> None:
        await self.store.ensure_skeleton()


__all__ = ["YggdrasilEngine"]