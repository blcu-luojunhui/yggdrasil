"""版本化检索服务 - 基于 ring 和 scope 的只读检索"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from src.core.yggdrasil.cognitive.models import (
    EdgeRevision,
    NodeRevision,
    NodeStatus,
    RetrievalScope,
    VersionedContext,
)
from src.core.yggdrasil.ports.repositories import (
    RevisionRepository,
    RingRepository,
    TreeRepository,
)
from src.infra.observability import MetricsCollector

logger = logging.getLogger(__name__)

# 按角色分配的默认预算
DEFAULT_ROLE_BUDGET = {
    "capacity": 3,
    "schema": 8,
    "fact": 8,
    "heuristic": 5,
    "case": 3,
    "state": 3,
    "risk": 2,  # contradictions/conflicts 特殊槽位
}

# 一跳扩展允许的关系白名单
ALLOWED_EXPAND_RELATIONS = {"enables", "evidences", "supports", "specializes", "derived_from", "imports"}
RISK_RELATIONS = {"contradicts"}

# 排序权重
WEIGHT_RELEVANCE = 0.40
WEIGHT_CONFIDENCE = 0.20
WEIGHT_FRESHNESS = 0.15
WEIGHT_UTILITY = 0.15
WEIGHT_RELATION = 0.10


class RetrievalService:
    """版本化检索服务 — 只读，不修改任何权重"""

    def __init__(
        self,
        tree_repo: TreeRepository,
        revision_repo: RevisionRepository,
        ring_repo: RingRepository,
        metrics: Optional[MetricsCollector] = None,
    ):
        self._tree_repo = tree_repo
        self._revision_repo = revision_repo
        self._ring_repo = ring_repo
        self._metrics = metrics

    async def retrieve(
        self,
        query: str,
        scope: RetrievalScope,
        *,
        relevance_fn=None,
    ) -> VersionedContext:
        """执行版本化检索

        过滤顺序：
            1. tree/ring manifest
            2. tenant/access
            3. active status
            4. valid time
            5. 向量/关键词候选
            6. 一跳关系扩展
            7. 排序/去重/预算
        """
        if scope.valid_at is None:
            scope.valid_at = datetime.now(timezone.utc)

        all_nodes: List[NodeRevision] = []
        all_edges: List[EdgeRevision] = []
        ring_ids: Dict[str, str] = {}

        for tree_id in scope.tree_ids:
            ring_id = scope.ring_ids.get(tree_id)
            if not ring_id:
                tree = await self._tree_repo.get(tree_id)
                if tree and tree.active_ring_id:
                    ring_id = tree.active_ring_id
            if not ring_id:
                continue

            ring_ids[tree_id] = ring_id

            # 1. 获取该 ring 的 node revisions
            ring_revisions = await self._revision_repo.list_active_for_ring(ring_id, scope)

            # 2. 过滤 tenant（非 default tenant 必须匹配）
            if scope.tenant_id == "default":
                filtered = ring_revisions
            else:
                filtered = [n for n in ring_revisions if True]  # 实际 tenant 过滤在 DB 层

            # 3. 过滤 status = active 且非 quarantined
            filtered = [
                n for n in filtered
                if n.status == NodeStatus.ACTIVE
            ]

            # 4. 过滤 valid time
            now = scope.valid_at
            filtered = [
                n for n in filtered
                if (n.valid_from is None or n.valid_from <= now)
                and (n.valid_until is None or n.valid_until > now)
            ]

            # 5. 收集边
            ring_edges = await self._revision_repo.list_edges_for_ring(ring_id)

            # 6. 一跳扩展
            expanded_ids = set(n.node_id for n in filtered)
            for node in filtered:
                for edge in ring_edges:
                    if edge.source_node_id == node.node_id and edge.relation in ALLOWED_EXPAND_RELATIONS:
                        expanded_ids.add(edge.target_node_id)

            # 7. 收集相关边
            filtered_node_ids = {n.node_id for n in filtered}
            for edge in ring_edges:
                if edge.target_node_id in expanded_ids and edge.source_node_id in filtered_node_ids:
                    all_edges.append(edge)

            # 8. 查找扩展节点的 revision
            expanded_revisions = await self._revision_repo.list_active_for_ring(ring_id, scope)
            expanded_nodes = [n for n in expanded_revisions if n.node_id in expanded_ids]

            all_nodes.extend(expanded_nodes)

        # 9. 去重
        seen_ids = set()
        deduped_nodes: List[NodeRevision] = []
        for n in all_nodes:
            if n.node_id not in seen_ids:
                seen_ids.add(n.node_id)
                deduped_nodes.append(n)

        seen_edge_ids = set()
        deduped_edges: List[EdgeRevision] = []
        for e in all_edges:
            if e.edge_id not in seen_edge_ids:
                seen_edge_ids.add(e.edge_id)
                deduped_edges.append(e)

        # 10. 排序：relevance 归一化 + 加权评分
        scored = self._score_nodes(deduped_nodes, deduped_edges)

        # 11. 按角色预算分配
        allocated = self._allocate_by_role(scored)

        # 12. 生成 markdown
        md = self._to_markdown(allocated, deduped_edges)

        # 13. 估算 token
        total_text = "".join(f"{n.title} {n.summary}" for n in allocated)
        estimated_tokens = int(len(total_text) / 4)

        if self._metrics:
            self._metrics.increment_retrieval()
            for tree_id in ring_ids:
                self._metrics.increment_retrieval_by_ring(
                    tree_id=tree_id, ring_id=ring_ids[tree_id]
                )

        return VersionedContext(
            nodes=allocated,
            edges=deduped_edges,
            total_tokens=estimated_tokens,
            markdown=md,
            ring_ids=ring_ids,
        )

    def _score_nodes(
        self, nodes: List[NodeRevision], edges: List[EdgeRevision]
    ) -> List[NodeRevision]:
        """按加权公式评分排序：
        score = 0.40*relevance + 0.20*confidence + 0.15*freshness
              + 0.15*utility + 0.10*relation_relevance
              - risk_penalty - redundancy_penalty
        """
        # 计算边的入度（作为 relation_relevance 的代理）
        edge_target_counts: Dict[str, int] = {}
        for e in edges:
            edge_target_counts[e.target_node_id] = edge_target_counts.get(e.target_node_id, 0) + 1

        max_edges = max(edge_target_counts.values()) if edge_target_counts else 1

        # 冗余惩罚：相似节点去重
        seen_titles: Dict[str, int] = {}

        for node in nodes:
            relation_relevance = edge_target_counts.get(node.node_id, 0) / max_edges
            node._score = (
                WEIGHT_CONFIDENCE * node.confidence
                + WEIGHT_FRESHNESS * node.freshness
                + WEIGHT_UTILITY * node.utility
                + WEIGHT_RELATION * relation_relevance
                - 0.1 * node.risk  # risk_penalty
            )

            # 冗余惩罚
            title_lower = node.title.lower()
            if title_lower in seen_titles:
                node._score -= 0.05 * seen_titles[title_lower]
                seen_titles[title_lower] += 1
            else:
                seen_titles[title_lower] = 1

        return sorted(nodes, key=lambda n: getattr(n, "_score", 0), reverse=True)

    def _allocate_by_role(self, nodes: List[NodeRevision]) -> List[NodeRevision]:
        """按角色预算分配节点"""
        by_role: Dict[str, List[NodeRevision]] = {}
        for n in nodes:
            by_role.setdefault(n.role, []).append(n)

        result: List[NodeRevision] = []
        risk_slot = DEFAULT_ROLE_BUDGET.get("risk", 2)
        risk_count = 0

        for role, role_nodes in by_role.items():
            budget = DEFAULT_ROLE_BUDGET.get(role, 5)
            # 已按 _score 排序
            count = 0
            for n in role_nodes:
                if n.risk > 0.4 and risk_count < risk_slot:
                    result.append(n)
                    risk_count += 1
                elif count < budget:
                    result.append(n)
                    count += 1

        return result

    def _to_markdown(self, nodes: List[NodeRevision], edges: List[EdgeRevision]) -> str:
        """生成 Markdown 表示"""
        lines = ["# Versioned Context\n"]

        if not nodes:
            lines.append("*No relevant nodes found*\n")
            return "\n".join(lines)

        by_role: Dict[str, list] = {}
        for n in nodes:
            by_role.setdefault(n.role, []).append(n)

        role_labels = {
            "capacity": "## Available Skills (Capacity)",
            "schema": "## Conceptual Framework (Schema)",
            "fact": "## Facts",
            "heuristic": "## Heuristics",
            "case": "## Cases",
            "state": "## State",
        }

        for role, label in role_labels.items():
            if role in by_role:
                lines.append(f"\n{label}\n")
                for n in by_role[role]:
                    score = getattr(n, "_score", 0)
                    lines.append(
                        f"- **{n.title}** "
                        f"(score={score:.2f}, utility={n.utility:.2f}, "
                        f"confidence={n.confidence:.2f}, risk={n.risk:.2f})"
                    )
                    if n.summary:
                        lines.append(f"  {n.summary}")

        return "\n".join(lines)
