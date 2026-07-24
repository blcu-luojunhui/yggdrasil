"""Skill Registry - 预注册的内存执行器"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol

logger = logging.getLogger(__name__)


@dataclass
class SkillResult:
    """技能执行结果"""
    success: bool
    output: Optional[str] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class SkillExecutor(Protocol):
    """技能执行器协议"""
    async def execute(self, payload: dict, timeout: float = 30.0) -> SkillResult: ...


class SkillRegistry:
    """预注册内存 Skill Registry

    不支持动态 Python import。所有 executor 必须在启动时注册。
    """

    def __init__(self):
        self._executors: Dict[str, SkillExecutor] = {}

    def register(self, executor_ref: str, executor: SkillExecutor) -> None:
        """注册执行器"""
        if executor_ref in self._executors:
            logger.warning(f"Overwriting existing executor: {executor_ref}")
        self._executors[executor_ref] = executor
        logger.info(f"Registered skill executor: {executor_ref}")

    def unregister(self, executor_ref: str) -> None:
        """注销执行器"""
        self._executors.pop(executor_ref, None)
        logger.info(f"Unregistered skill executor: {executor_ref}")

    def has_executor(self, executor_ref: str) -> bool:
        """检查执行器是否存在"""
        return executor_ref in self._executors

    def list_executors(self) -> List[str]:
        """列出所有注册的执行器"""
        return list(self._executors.keys())

    async def execute(
        self,
        executor_ref: str,
        payload: dict,
        timeout: float = 30.0,
    ) -> SkillResult:
        """执行技能

        Args:
            executor_ref: 执行器引用 ID
            payload: 输入参数
            timeout: 超时秒数

        Returns:
            SkillResult

        Raises:
            ValueError: 未知 executor_ref
        """
        executor = self._executors.get(executor_ref)
        if not executor:
            raise ValueError(f"Unknown executor_ref: {executor_ref}")

        logger.info(f"Executing skill: {executor_ref}, timeout={timeout}s")
        try:
            result = await executor.execute(payload, timeout)
            logger.info(f"Skill completed: {executor_ref}, success={result.success}")
            return result
        except Exception as e:
            logger.error(f"Skill failed: {executor_ref}, error={e}")
            return SkillResult(success=False, error=str(e))
