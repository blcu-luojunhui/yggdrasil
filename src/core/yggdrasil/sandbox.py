import logging
from typing import List, Optional
from datetime import datetime

from src.core.yggdrasil.models import (
    CognitiveNode,
    CognitiveEdge,
    Branch,
    RelationType,
)
from src.core.yggdrasil.store import YggdrasilStore, _uuid_v7
from src.core.yggdrasil.embedding import EmbeddingService

logger = logging.getLogger(__name__)


class SandboxManager:
    """沙盒分支管理器 - 安全探索，变异隔离"""

    MAIN_BRANCH = "main"

    def __init__(self, store: YggdrasilStore, embedding: EmbeddingService):
        self.store = store
        self.embedding = embedding

    async def ensure_main_branch(self) -> Branch:
        """确保 main 分支存在"""
        rows = await self.store.db.async_fetch(
            "SELECT * FROM branch WHERE name = ?", (self.MAIN_BRANCH,)
        )
        if rows:
            b = rows[0]
            return Branch(
                id=b["id"], name=b["name"], parent_branch_id=b.get("parent_branch_id"),
                status=b["status"], created_at=b.get("created_at"), created_by=b.get("created_by"),
            )

        branch = Branch(id=_uuid_v7(), name=self.MAIN_BRANCH, status="active")
        await self.store.db.async_save(
            "INSERT INTO branch (id, name, status) VALUES (?, ?, ?)",
            (branch.id, branch.name, branch.status),
        )
        logger.info("Main branch created")
        return branch

    async def fork(self, sandbox_name: str, created_by: Optional[str] = None) -> Branch:
        """从 main 分支 fork 一个沙盒"""
        main = await self.ensure_main_branch()

        branch = Branch(
            id=_uuid_v7(),
            name=sandbox_name,
            parent_branch_id=main.id,
            status="active",
            created_by=created_by,
        )
        await self.store.db.async_save(
            "INSERT INTO branch (id, name, parent_branch_id, status, created_by) VALUES (?, ?, ?, ?, ?)",
            (branch.id, branch.name, branch.parent_branch_id, branch.status, branch.created_by),
        )
        logger.info(f"Sandbox forked: {sandbox_name} (id={branch.id})")
        return branch

    async def get_branch(self, branch_id: str) -> Optional[Branch]:
        row = await self.store.db.async_fetch_one("SELECT * FROM branch WHERE id = ?", (branch_id,))
        if not row:
            return None
        return Branch(
            id=row["id"], name=row["name"], parent_branch_id=row.get("parent_branch_id"),
            status=row["status"], created_at=row.get("created_at"), created_by=row.get("created_by"),
        )

    async def list_sandboxes(self) -> List[Branch]:
        rows = await self.store.db.async_fetch(
            "SELECT * FROM branch WHERE name != ? ORDER BY created_at DESC", (self.MAIN_BRANCH,)
        )
        return [
            Branch(
                id=r["id"], name=r["name"], parent_branch_id=r.get("parent_branch_id"),
                status=r["status"], created_at=r.get("created_at"), created_by=r.get("created_by"),
            )
            for r in rows
        ]

    async def create_node_in_sandbox(
        self, branch_id: str, node: CognitiveNode,
    ) -> CognitiveNode:
        """在沙盒中创建节点（正常创建，通过分支 ID 标记隔离）"""
        branch = await self.get_branch(branch_id)
        if not branch or branch.status != "active":
            raise ValueError(f"Sandbox {branch_id} not active")

        # 节点直接创建，沙盒隔离通过 branch 表记录
        # Phase 3 会用 cog_node_version 实现更完整的版本隔离
        node.id = node.id or _uuid_v7()
        await self.store.create_node(node)
        await self.embedding.upsert_node(node)

        logger.debug(f"Node {node.id} created in sandbox {branch_id}")
        return node

    async def export_changes(self, branch_id: str) -> dict:
        """导出沙盒中的变更（Phase 1: 简化版，直接统计节点）"""
        branch = await self.get_branch(branch_id)
        if not branch:
            return {"error": "Sandbox not found"}

        # Phase 1: 简化版，只统计
        nodes = await self.store.list_nodes(min_health=0.0)
        created = len(nodes)

        return {
            "branch_id": branch_id,
            "branch_name": branch.name,
            "status": branch.status,
            "nodes_total": created,
            "message": "Placeholder: detailed diff will be available in Phase 3 with version tables",
        }

    async def merge(self, branch_id: str, reason: Optional[str] = None) -> dict:
        """合并沙盒到主干"""
        branch = await self.get_branch(branch_id)
        if not branch or branch.status != "active":
            raise ValueError(f"Sandbox {branch_id} not active or not found")

        # Phase 1: 标记分支为 merged
        # Phase 3: 实际合并变更到激活版本视图
        await self.store.db.async_save(
            "UPDATE branch SET status = 'archived' WHERE id = ?", (branch_id,)
        )
        logger.info(f"Sandbox {branch_id} ({branch.name}) merged: {reason or 'no reason'}")

        return {
            "branch_id": branch_id,
            "branch_name": branch.name,
            "action": "merged",
            "message": "Phase 1 merge: all nodes preserved. Detailed merge in Phase 3.",
        }

    async def discard(self, branch_id: str, reason: Optional[str] = None) -> dict:
        """丢弃沙盒，隔离有害变异"""
        branch = await self.get_branch(branch_id)
        if not branch or branch.status != "active":
            raise ValueError(f"Sandbox {branch_id} not active or not found")

        # 标记所有该分支创建的节点为隔离（health = 0）
        # Phase 1 简化版：标记分支状态
        await self.store.db.async_save(
            "UPDATE branch SET status = 'isolated' WHERE id = ?", (branch_id,)
        )
        logger.warning(f"Sandbox {branch_id} ({branch.name}) discarded and isolated: {reason or 'assessment failed'}")

        return {
            "branch_id": branch_id,
            "branch_name": branch.name,
            "action": "isolated",
            "message": "Sandbox discarded and marked as isolated for audit. Full rollback in Phase 3.",
        }

    async def discard_and_rollback(self, branch_id: str, reason: Optional[str] = None) -> dict:
        """丢弃并回滚：删除沙盒中创建的所有节点"""
        branch = await self.get_branch(branch_id)
        if not branch or branch.status != "active":
            raise ValueError(f"Sandbox {branch_id} not active")

        # 记录操作
        await self.store.db.async_save(
            "UPDATE branch SET status = 'isolated' WHERE id = ?", (branch_id,)
        )
        logger.info(f"Sandbox {branch_id} rolled back: {reason or 'no reason'}")

        return {
            "branch_id": branch_id,
            "branch_name": branch.name,
            "action": "rollback",
            "message": "Sandbox discarded. Full version rollback in Phase 3.",
        }

    async def evaluate(self, branch_id: str, success: bool, reason: Optional[str] = None) -> dict:
        """评估沙盒结果"""
        if success:
            return await self.merge(branch_id, reason)
        else:
            return await self.discard(branch_id, reason)


__all__ = ["SandboxManager"]
