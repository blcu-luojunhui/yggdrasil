"""Run 服务 - Agent 运行追踪"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from src.core.yggdrasil.cognitive.models import RunStatus
from src.core.yggdrasil.ports.repositories import (
    RunRepository,
    TreeRepository,
)
from src.core.yggdrasil.runtime.models import (
    AgentRun,
    RunEdgeReference,
    RunNodeReference,
)
from src.infra.execution.skill_registry import SkillRegistry
from src.infra.observability import MetricsCollector

logger = logging.getLogger(__name__)


class RunService:
    """Agent 运行服务"""

    def __init__(
        self,
        run_repo: RunRepository,
        tree_repo: TreeRepository,
        skill_registry: SkillRegistry,
        metrics: Optional[MetricsCollector] = None,
    ):
        self._run_repo = run_repo
        self._tree_repo = tree_repo
        self._skill_registry = skill_registry
        self._metrics = metrics

    async def start_run(
        self,
        intent: str,
        tenant_id: str = "default",
        forest_release_id: Optional[str] = None,
    ) -> AgentRun:
        """创建并启动一个 Run"""
        run = AgentRun(
            run_id="",
            tenant_id=tenant_id,
            intent=intent,
            forest_release_id=forest_release_id,
            status=RunStatus.RUNNING,
            started_at=datetime.now(timezone.utc),
        )
        run_id = await self._run_repo.create(run)
        run.run_id = run_id
        logger.info(f"Run started: {run_id} (intent={intent})")
        return run

    async def record_context(
        self,
        run_id: str,
        context,
    ):
        """记录检索上下文引用"""
        nodes = []
        for rank, node in enumerate(getattr(context, "nodes", []), start=1):
            revision_id = getattr(node, "revision_id", None) or getattr(node, "id", None)
            if not revision_id:
                continue
            nodes.append({
                "revision_id": revision_id,
                "rank": rank,
                "score": getattr(node, "_score", getattr(node, "utility", getattr(node, "strength", 0.0))),
                "usage_type": "retrieved",
            })
        edges = [
            {"revision_id": getattr(edge, "revision_id", None) or getattr(edge, "id", None)}
            for edge in getattr(context, "edges", [])
            if getattr(edge, "revision_id", None) or getattr(edge, "id", None)
        ]
        return await self.record_references(run_id, nodes=nodes, edges=edges)

    async def record_references(
        self,
        run_id: str,
        *,
        nodes: Optional[list[dict]] = None,
        edges: Optional[list[dict]] = None,
    ) -> dict:
        """记录一次 Run 使用到的节点/边修订引用。

        引用表使用 ``INSERT OR IGNORE``，因此网络重试是安全的；同一
        ``run_id`` 不存在时提前报错，避免产生孤儿引用。
        """
        if not await self._run_repo.get(run_id):
            raise ValueError(f"Run not found: {run_id}")

        node_count = 0
        for item in nodes or []:
            revision_id = str(item.get("revision_id", "")).strip()
            if not revision_id:
                raise ValueError("Each node reference requires revision_id")
            ref = RunNodeReference(
                run_id=run_id,
                revision_id=revision_id,
                rank=int(item.get("rank", 0)),
                score=float(item.get("score", 0.0)),
                usage_type=item.get("usage_type", "retrieved"),
            )
            await self._run_repo.add_node_reference(ref)
            node_count += 1

        edge_count = 0
        for item in edges or []:
            revision_id = str(item.get("revision_id", "")).strip()
            if not revision_id:
                raise ValueError("Each edge reference requires revision_id")
            await self._run_repo.add_edge_reference(RunEdgeReference(
                run_id=run_id,
                revision_id=revision_id,
            ))
            edge_count += 1
        return {"nodes": node_count, "edges": edge_count}

    async def record_action_result(
        self,
        run_id: str,
        skill_revision_id: str,
        input_payload: Optional[Dict[str, Any]] = None,
        output_ref: str = "",
        status: str = "completed",
    ) -> str:
        """记录动作执行结果"""
        import hashlib
        from src.core.yggdrasil.runtime.models import ActionResult

        run = await self._run_repo.get(run_id)
        if not run:
            raise ValueError(f"Run not found: {run_id}")
        if run.status != RunStatus.RUNNING:
            raise ValueError(f"Run {run_id} is not running")

        input_hash = ""
        if input_payload:
            input_hash = hashlib.sha256(
                json.dumps(input_payload, sort_keys=True).encode()
            ).hexdigest()

        result = ActionResult(
            run_id=run_id,
            skill_revision_id=skill_revision_id,
            input_payload=input_payload,
            input_hash=input_hash,
            output_ref=output_ref,
            status=status,
        )
        await self._run_repo.add_action_result(result)
        logger.info(
            f"Action result recorded: run={run_id}, skill={skill_revision_id}, "
            f"status={status}, input_hash={input_hash[:12]}..."
        )
        return skill_revision_id

    async def finish_run(
        self,
        run_id: str,
        status: RunStatus,
        result_ref: Optional[str] = None,
    ) -> None:
        """结束 Run — 只允许从 running 状态进入终态"""
        if status == RunStatus.RUNNING:
            raise ValueError("Run can only finish with a terminal status")
        run = await self._run_repo.get(run_id)
        if not run:
            raise ValueError(f"Run not found: {run_id}")
        if run.status != RunStatus.RUNNING:
            raise ValueError(
                f"Run {run_id} has status {run.status.value}, "
                f"can only finish from 'running'"
            )
        await self._run_repo.finish(run_id, status.value, result_ref)
        logger.info(f"Run finished: {run_id} (status={status.value})")

    async def get_run(self, run_id: str) -> Optional[AgentRun]:
        return await self._run_repo.get(run_id)

    async def execute_skill(
        self,
        executor_ref: str,
        payload: dict,
        timeout: float = 30.0,
    ) -> str:
        """执行技能并返回执行引用"""
        result = await self._skill_registry.execute(executor_ref, payload, timeout)
        return result.output or ""
