"""Evaluation 服务 - 评价记录（不直接修改知识）"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.core.yggdrasil.evaluation.models import Evaluation
from src.core.yggdrasil.ports.repositories import EvaluationRepository

logger = logging.getLogger(__name__)


class EvaluationService:
    """评价服务"""

    def __init__(self, eval_repo: EvaluationRepository):
        self._eval_repo = eval_repo

    async def record_evaluation(
        self,
        run_id: str,
        technical_success: float = 0.0,
        task_success: float = 0.0,
        result_quality: float = 0.0,
        safety: float = 1.0,
        user_feedback: Optional[str] = None,
        attribution: Optional[Dict[str, Any]] = None,
        evaluator_type: str = "system",
    ) -> str:
        """记录评价（不修改任何知识权重）"""
        evaluation = Evaluation(
            evaluation_id="",
            run_id=run_id,
            evaluator_type=evaluator_type,
            technical_success=technical_success,
            task_success=task_success,
            result_quality=result_quality,
            safety=safety,
            user_feedback=user_feedback,
            attribution=attribution,
            created_at=datetime.now(timezone.utc),
        )
        eval_id = await self._eval_repo.create(evaluation)
        logger.info(f"Evaluation recorded: {eval_id} (run={run_id})")
        return eval_id

    async def get_evaluations(self, run_id: str) -> List[Evaluation]:
        return await self._eval_repo.list_by_run(run_id)

    # 别名，兼容测试
    async def create_evaluation(
        self,
        run_id: str,
        technical_success: float = 0.0,
        task_success: float = 0.0,
        result_quality: float = 0.0,
        safety: float = 1.0,
        user_feedback: Optional[str] = None,
        attribution: Optional[Dict[str, Any]] = None,
        evaluator_type: str = "system",
    ) -> str:
        return await self.record_evaluation(
            run_id=run_id,
            technical_success=technical_success,
            task_success=task_success,
            result_quality=result_quality,
            safety=safety,
            user_feedback=user_feedback,
            attribution=attribution,
            evaluator_type=evaluator_type,
        )

    async def list_by_run(self, run_id: str) -> List[Evaluation]:
        return await self._eval_repo.list_by_run(run_id)
