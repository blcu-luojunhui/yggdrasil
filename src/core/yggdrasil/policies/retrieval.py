"""检索策略：排序、去重、风险惩罚"""

from typing import Dict, List, Protocol

from ..cognitive.models import NodeRevision


class RetrievalPolicy(Protocol):
    """检索策略协议"""
    async def score(self, node: NodeRevision, query_relevance: float) -> float: ...
    async def rank(self, nodes: List[NodeRevision], relevance: Dict[str, float]) -> List[NodeRevision]: ...


async def default_scoring(
    node: NodeRevision,
    relevance: float,
    *,
    w_relevance: float = 0.40,
    w_confidence: float = 0.20,
    w_freshness: float = 0.15,
    w_utility: float = 0.15,
    w_relation: float = 0.10,
    risk_penalty: float = 0.5,
    redundancy_penalty: float = 0.2,
) -> float:
    """默认加权排序

    公式：
        base = 0.40 * relevance + 0.20 * confidence + 0.15 * freshness
             + 0.15 * utility + 0.10 * relation_relevance
        score = base - risk_penalty * node.risk - redundancy_penalty (可重入时扣)
    """
    base = (
        w_relevance * relevance
        + w_confidence * node.confidence
        + w_freshness * node.freshness
        + w_utility * node.utility
        + w_relation * relevance  # relation_relevance 先用 query_relevance 代理
    )
    penalty = risk_penalty * node.risk
    return max(0.0, base - penalty)
