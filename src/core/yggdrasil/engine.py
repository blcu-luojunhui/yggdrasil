import logging
from typing import Optional, List

from src.core.config import YggdrasilConfig
from src.core.yggdrasil.models import (
    Domain,
    CognitiveNode,
    CognitiveEdge,
    CognitiveRole,
    RelationType,
    SubtreeContext,
    ChangeLogEntry,
)
from src.core.yggdrasil.store import YggdrasilStore
from src.core.yggdrasil.retriever import SubtreeRetriever
from src.core.yggdrasil.embedding import EmbeddingService
from src.infra.observability import MetricsCollector

logger = logging.getLogger(__name__)


class YggdrasilEngine:
    """
    Yggdrasil 世界树引擎 - 整合存储、检索、进化为统一接口

    核心 API:
    - retrieve: 检索认知子树供 LLM 使用
    - create_node: 创建新认知节点
    - create_edge: 创建/更新边
    - feedback: 执行后反馈，更新强度
    - get_markdown_context: 获取 Markdown 格式上下文注入 prompt
    """

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

    async def retrieve(
        self,
        query: str,
        domain_path: Optional[str] = None,
        max_nodes: Optional[int] = None,
    ) -> SubtreeContext:
        """检索认知子树"""
        self.metrics.increment_retrieval()
        context = await self.retriever.retrieve(query, domain_path, max_nodes)
        self.metrics.observe_retrieval_nodes(len(context.nodes))
        return context

    async def get_markdown_context(self, query: str, domain_path: Optional[str] = None) -> str:
        """获取 Markdown 格式的认知上下文，直接注入 prompt"""
        context = await self.retrieve(query, domain_path)
        return context.to_markdown()

    async def create_domain(
        self,
        domain_name: str,
        parent_path: Optional[str] = None,
    ) -> Domain:
        """创建新领域"""
        if parent_path is None:
            # 创建顶级领域
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

        domain = Domain(
            parent_id=parent_id,
            domain_name=domain_name,
            full_path=full_path,
            depth=depth,
        )
        domain.id = await self.store.create_domain(domain)
        return domain

    async def create_node(
        self,
        domain_path: str,
        role: CognitiveRole,
        node_name: str,
        content: Optional[str] = None,
        description: Optional[str] = None,
        generate_embedding: bool = True,
    ) -> CognitiveNode:
        """创建新认知节点"""
        domain = await self.store.get_domain_by_path(domain_path)
        if not domain:
            raise ValueError(f"Domain {domain_path} not found")

        # 生成嵌入
        embedding_bytes = None
        if generate_embedding and content:
            emb = await self.embedding.embed_text(f"{node_name}\n{description or ''}\n{content}")
            embedding_bytes = self.embedding.serialize(emb)

        node = CognitiveNode(
            domain_id=domain.id,
            role=role,
            node_name=node_name,
            description=description,
            content=content,
            embedding=embedding_bytes,
        )
        node.id = await self.store.create_node(node)
        self.metrics.increment_node_created(role.value)

        # 更新计数
        for r in CognitiveRole:
            cnt = await self.store.count_nodes_by_role().get(r, 0)
            self.metrics.set_node_count(r.value, cnt)

        return node

    async def add_edge(
        self,
        from_node: int,
        to_node: int,
        relation_type: RelationType,
        strength: float = 0.5,
        source: Optional[str] = None,
    ) -> int:
        """添加或更新边"""
        edge = CognitiveEdge(
            from_node_id=from_node,
            to_node_id=to_node,
            relation_type=relation_type,
            strength=strength,
            source=source,
        )
        edge.id = await self.store.create_edge(edge)
        self.metrics.increment_edge_updated(relation_type.value)
        return edge.id

    async def feedback(
        self,
        node_id: Optional[int] = None,
        edge_id: Optional[int] = None,
        success: bool = True,
        step: float = 0.1,
        trace_id: Optional[str] = None,
    ) -> None:
        """
        执行后反馈：成功 strengthen，失败 weaken

        强度在 [0,1] 区间裁剪
        """
        if node_id:
            node = await self.store.get_node(node_id)
            if node:
                delta = step if success else -step
                new_strength = max(0.0, min(1.0, node.strength + delta))
                await self.store.update_node_strength(node_id, new_strength)

                # 记录变更日志
                if trace_id:
                    log = ChangeLogEntry(
                        node_id=node_id,
                        operation="update_strength",
                        old_values={"strength": node.strength},
                        new_values={"strength": new_strength},
                        reason="feedback" + (" success" if success else " failure"),
                        trace_id=trace_id,
                    )
                    await self.store.log_change(log)

        if edge_id:
            edge = await self.store.get_edge(edge_id)
            if edge:
                delta = step if success else -step
                new_strength = max(0.0, min(1.0, edge.strength + delta))
                await self.store.update_edge_strength(edge_id, new_strength)

                if trace_id:
                    log = ChangeLogEntry(
                        edge_id=edge_id,
                        operation="update_strength",
                        old_values={"strength": edge.strength},
                        new_values={"strength": new_strength},
                        reason="feedback" + (" success" if success else " failure"),
                        trace_id=trace_id,
                    )
                    await self.store.log_change(log)

    async def strengthen(
        self,
        from_node: int,
        to_node: int,
        relation_type: RelationType,
        step: float = 0.1,
        source: str = "execution",
        trace_id: Optional[str] = None,
    ) -> None:
        """强化关联：成功执行后强化边"""
        edge = await self.store.get_edge_between(from_node, to_node, relation_type)
        if edge:
            new_strength = min(1.0, edge.strength + step)
            await self.store.update_edge_strength(edge.id, new_strength)
            if trace_id:
                log = ChangeLogEntry(
                    edge_id=edge.id,
                    operation="update_strength",
                    old_values={"strength": edge.strength},
                    new_values={"strength": new_strength},
                    reason="strengthen from " + source,
                    trace_id=trace_id,
                )
                await self.store.log_change(log)
        else:
            # 创建新边
            await self.add_edge(from_node, to_node, relation_type, strength=0.5 + step, source=source)

    async def get_node(self, node_id: int) -> Optional[CognitiveNode]:
        """获取节点"""
        return await self.store.get_node(node_id)

    async def list_nodes(self, domain_path: str) -> List[CognitiveNode]:
        """列出领域下所有节点"""
        domain = await self.store.get_domain_by_path(domain_path)
        if not domain:
            return []
        return await self.store.list_nodes_by_domain(domain.id, include_isolated=False)

    async def ensure_skeleton(self) -> None:
        """确保基础骨架存在"""
        await self.store.ensure_skeleton()

    def _update_metrics(self):
        """更新 Prometheus 指标"""
        counts = self.store.count_nodes_by_role()
        for role, cnt in counts.items():
            self.metrics.set_node_count(role.value, cnt)


__all__ = ["YggdrasilEngine"]
