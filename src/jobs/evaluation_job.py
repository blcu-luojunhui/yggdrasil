"""Evaluation Job - 异步评估已完成的 Run"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from src.core.config import YggdrasilConfig
from src.core.yggdrasil.cognitive.models import RunStatus
from src.core.yggdrasil.ports.repositories import EvaluationRepository, RunRepository
from src.infra.observability import LogService

logger = logging.getLogger(__name__)


class EvaluationJob:
    """Evaluation Job（当前为占位实现）"""

    def __init__(
        self,
        run_repo: RunRepository,
        eval_repo: EvaluationRepository,
        config: YggdrasilConfig,
        log_service: Optional[LogService] = None,
    ):
        self._run_repo = run_repo
        self._eval_repo = eval_repo
        self._config = config
        self._log_service = log_service
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self, interval: float = 30.0):
        self._running = True
        self._task = asyncio.create_task(self._run_loop(interval))
        logger.info("EvaluationJob started")

    async def stop(self, timeout: float = 10.0):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await asyncio.wait_for(self._task, timeout=timeout)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
        logger.info("EvaluationJob stopped")

    async def _run_loop(self, interval: float):
        while self._running:
            try:
                # 查找已完成的 Run
                succeeded_runs = await self._run_repo.list_by_status(
                    RunStatus.SUCCEEDED.value, limit=20
                )
                failed_runs = await self._run_repo.list_by_status(
                    RunStatus.FAILED.value, limit=10
                )
                runs_to_evaluate = succeeded_runs + failed_runs

                for run in runs_to_evaluate:
                    try:
                        # 检查是否已有评价
                        existing = await self._eval_repo.list_by_run(run.run_id)
                        if existing:
                            continue

                        is_success = run.status == RunStatus.SUCCEEDED
                        # 根据成功/失败生成基础评价
                        from datetime import datetime, timezone
                        from src.core.yggdrasil.evaluation.models import Evaluation

                        eval_record = Evaluation(
                            evaluation_id="",
                            run_id=run.run_id,
                            evaluator_type="system",
                            technical_success=1.0 if is_success else 0.0,
                            task_success=1.0 if is_success else 0.0,
                            result_quality=0.5,  # 中性
                            safety=1.0,
                            created_at=datetime.now(timezone.utc),
                        )
                        await self._eval_repo.create(eval_record)
                        logger.info(
                            f"Auto-evaluation created for run {run.run_id}: "
                            f"{'succeeded' if is_success else 'failed'}"
                        )
                    except Exception as e:
                        logger.warning(
                            f"Failed to evaluate run {run.run_id}: {e}"
                        )
            except Exception as e:
                logger.warning(f"Evaluation poll error: {e}")
            await asyncio.sleep(interval)
