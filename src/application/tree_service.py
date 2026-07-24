"""Tree 服务 - 树清单和节点管理"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from src.core.yggdrasil.cognitive.models import (
    NodeRevision,
    NodeStatus,
    TreeManifest,
)
from src.core.yggdrasil.ports.repositories import (
    RevisionRepository,
    RingRepository,
    TreeRepository,
)
from src.infra.observability import MetricsCollector

logger = logging.getLogger(__name__)


class TreeService:
    """树服务"""

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

    async def create_tree(
        self,
        name: str,
        bounded_context: str = "",
        tenant_id: str = "default",
        owner: str = "",
    ) -> TreeManifest:
        """创建树"""
        from src.core.yggdrasil.store import _uuid_v7
        tree = TreeManifest(
            tree_id=_uuid_v7(),
            tenant_id=tenant_id,
            name=name,
            bounded_context=bounded_context,
            owner=owner,
        )
        tree_id = await self._tree_repo.create(tree)
        tree.tree_id = tree_id
        logger.info(f"Tree created: {tree_id} (name={name})")
        return tree

    async def get_tree(self, tree_id: str) -> Optional[TreeManifest]:
        return await self._tree_repo.get(tree_id)

    async def list_trees(self, tenant_id: str = "default") -> List[TreeManifest]:
        return await self._tree_repo.list(tenant_id)

    async def create_candidate_node(
        self,
        tree_id: str,
        role: str = "fact",
        title: str = "",
        summary: str = "",
        payload: Optional[Dict[str, Any]] = None,
        author_id: str = "system",
        change_reason: str = "",
    ) -> NodeRevision:
        """创建候选节点修订（不直接进入 active ring）"""
        from src.core.yggdrasil.store import _uuid_v7
        import hashlib
        import json

        content_hash = hashlib.sha256(
            json.dumps(payload or {}, sort_keys=True).encode()
        ).hexdigest()

        rev = NodeRevision(
            revision_id=_uuid_v7(),
            node_id=_uuid_v7(),
            tree_id=tree_id,
            role=role,
            title=title,
            summary=summary,
            payload=payload,
            status=NodeStatus.CANDIDATE,
            author_id=author_id,
            change_reason=change_reason,
            content_hash=content_hash,
        )
        rev_id = await self._revision_repo.create_node(rev)
        rev.revision_id = rev_id
        logger.info(f"Candidate node created: {rev.node_id} (tree={tree_id})")
        return rev
