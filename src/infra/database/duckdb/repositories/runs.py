"""RunRepository & EvaluationRepository — Agent 运行记录与评价持久化"""

import json
import logging
from datetime import datetime, timezone
from typing import List, Optional

from src.core.yggdrasil.cognitive.models import RunStatus
from src.core.yggdrasil.evaluation.models import Evaluation
from src.core.yggdrasil.runtime.models import (
    ActionResult,
    AgentRun,
    RunEdgeReference,
    RunNodeReference,
)
from src.infra.database.duckdb.pool import DuckDBPool

from . import _uuid_v7

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    """DuckDB TIMESTAMP 不带时区，统一写入 naive UTC。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class DuckDBRunRepository:
    """DuckDB 实现的 RunRepository"""

    def __init__(self, pool: DuckDBPool):
        self.pool = pool

    async def create(self, run: AgentRun) -> str:
        """创建一条 Agent 运行记录"""
        run_id = run.run_id or _uuid_v7()
        now = _utcnow()

        await self.pool.async_save(
            """INSERT INTO agent_run (
                   run_id, tenant_id, intent, forest_release_id, soil_checkpoint,
                   prompt_context_hash, selected_skill_revision_id, decision_trace_ref,
                   result_ref, status, started_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run_id,
                run.tenant_id,
                run.intent,
                run.forest_release_id,
                run.soil_checkpoint,
                run.prompt_context_hash,
                run.selected_skill_revision_id,
                run.decision_trace_ref,
                run.result_ref,
                run.status.value if isinstance(run.status, RunStatus) else run.status,
                now,
            ),
        )
        return run_id

    async def get(self, run_id: str) -> Optional[AgentRun]:
        """获取运行记录"""
        row = await self.pool.async_fetch_one(
            "SELECT * FROM agent_run WHERE run_id = ?", (run_id,)
        )
        if not row:
            return None
        return AgentRun(
            run_id=row["run_id"],
            tenant_id=row.get("tenant_id", "default"),
            intent=row.get("intent", ""),
            forest_release_id=row.get("forest_release_id"),
            soil_checkpoint=row.get("soil_checkpoint"),
            prompt_context_hash=row.get("prompt_context_hash"),
            selected_skill_revision_id=row.get("selected_skill_revision_id"),
            decision_trace_ref=row.get("decision_trace_ref"),
            result_ref=row.get("result_ref"),
            status=RunStatus(row.get("status", "running")),
            started_at=row.get("started_at"),
            completed_at=row.get("completed_at"),
        )

    async def add_node_reference(self, ref: RunNodeReference) -> None:
        """添加节点引用"""
        await self.pool.async_save(
            "INSERT OR IGNORE INTO run_node_reference (run_id, revision_id, rank, score, usage_type) VALUES (?, ?, ?, ?, ?)",
            (ref.run_id, ref.revision_id, ref.rank, ref.score, ref.usage_type),
        )

    async def add_edge_reference(self, ref: RunEdgeReference) -> None:
        """添加边引用"""
        await self.pool.async_save(
            "INSERT OR IGNORE INTO run_edge_reference (run_id, revision_id) VALUES (?, ?)",
            (ref.run_id, ref.revision_id),
        )

    async def list_node_references(self, run_id: str) -> List[dict]:
        return await self.pool.async_fetch(
            """SELECT revision_id, rank, score, usage_type
               FROM run_node_reference WHERE run_id = ? ORDER BY rank, revision_id""",
            (run_id,),
        )

    async def list_edge_references(self, run_id: str) -> List[dict]:
        return await self.pool.async_fetch(
            "SELECT revision_id FROM run_edge_reference WHERE run_id = ? ORDER BY revision_id",
            (run_id,),
        )

    async def add_action_result(self, result: ActionResult) -> str:
        """添加动作执行结果"""
        await self.pool.async_save(
            """INSERT OR REPLACE INTO action_result (
                   run_id, skill_revision_id, input_payload, input_hash,
                   output_ref, status, started_at, completed_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                result.run_id,
                result.skill_revision_id,
                json.dumps(result.input_payload) if result.input_payload else None,
                result.input_hash,
                result.output_ref,
                result.status,
                result.started_at or _utcnow(),
                result.completed_at or _utcnow(),
            ),
        )
        return result.skill_revision_id

    async def list_action_results(self, run_id: str) -> List[dict]:
        rows = await self.pool.async_fetch(
            """SELECT skill_revision_id, input_payload, input_hash, output_ref,
                      status, started_at, completed_at
               FROM action_result WHERE run_id = ? ORDER BY started_at""",
            (run_id,),
        )
        for row in rows:
            if isinstance(row.get("input_payload"), str):
                try:
                    row["input_payload"] = json.loads(row["input_payload"])
                except json.JSONDecodeError:
                    pass
        return rows

    async def finish(self, run_id: str, status: str, result_ref: Optional[str] = None) -> None:
        """结束运行"""
        completed_at = _utcnow()
        if result_ref:
            await self.pool.async_save(
                "UPDATE agent_run SET status = ?, result_ref = ?, completed_at = ? WHERE run_id = ?",
                (status, result_ref, completed_at, run_id),
            )
        else:
            await self.pool.async_save(
                "UPDATE agent_run SET status = ?, completed_at = ? WHERE run_id = ?",
                (status, completed_at, run_id),
            )

    async def list_by_status(self, status: str, limit: int = 50) -> List[AgentRun]:
        """按状态列出运行记录"""
        rows = await self.pool.async_fetch(
            "SELECT * FROM agent_run WHERE status = ? ORDER BY started_at DESC LIMIT ?",
            (status, limit),
        )
        return [
            AgentRun(
                run_id=row["run_id"],
                tenant_id=row.get("tenant_id", "default"),
                intent=row.get("intent", ""),
                forest_release_id=row.get("forest_release_id"),
                soil_checkpoint=row.get("soil_checkpoint"),
                prompt_context_hash=row.get("prompt_context_hash"),
                selected_skill_revision_id=row.get("selected_skill_revision_id"),
                decision_trace_ref=row.get("decision_trace_ref"),
                result_ref=row.get("result_ref"),
                status=RunStatus(row.get("status", "running")),
                started_at=row.get("started_at"),
                completed_at=row.get("completed_at"),
            )
            for row in rows
        ]


class DuckDBEvaluationRepository:
    """DuckDB 实现的 EvaluationRepository"""

    def __init__(self, pool: DuckDBPool):
        self.pool = pool

    async def create(self, evaluation: Evaluation) -> str:
        """创建评价记录"""
        evaluation_id = evaluation.evaluation_id or _uuid_v7()
        now = _utcnow()

        await self.pool.async_save(
            """INSERT INTO evaluation (
                   evaluation_id, run_id, evaluator_type, technical_success,
                   task_success, result_quality, safety, user_feedback,
                   delayed_outcome, attribution, created_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                evaluation_id,
                evaluation.run_id,
                evaluation.evaluator_type,
                evaluation.technical_success,
                evaluation.task_success,
                evaluation.result_quality,
                evaluation.safety,
                evaluation.user_feedback,
                evaluation.delayed_outcome,
                json.dumps(evaluation.attribution) if evaluation.attribution else None,
                now,
            ),
        )
        return evaluation_id

    async def list_by_run(self, run_id: str) -> List[Evaluation]:
        """列出一个运行的所有评价"""
        rows = await self.pool.async_fetch(
            "SELECT * FROM evaluation WHERE run_id = ? ORDER BY created_at", (run_id,)
        )
        results: List[Evaluation] = []
        for row in rows:
            attribution_raw = row.get("attribution")
            results.append(Evaluation(
                evaluation_id=row["evaluation_id"],
                run_id=row["run_id"],
                evaluator_type=row.get("evaluator_type", "system"),
                technical_success=float(row.get("technical_success", 0.0)),
                task_success=float(row.get("task_success", 0.0)),
                result_quality=float(row.get("result_quality", 0.0)),
                safety=float(row.get("safety", 1.0)),
                user_feedback=row.get("user_feedback"),
                delayed_outcome=row.get("delayed_outcome"),
                attribution=json.loads(attribution_raw) if isinstance(attribution_raw, str) else attribution_raw,
                created_at=row.get("created_at"),
            ))
        return results
