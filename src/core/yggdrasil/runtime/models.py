"""运行时模型：Agent Run、引用、执行结果"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel

from ..cognitive.models import RunStatus


class AgentRun(BaseModel):
    """Agent 运行记录"""
    run_id: str
    tenant_id: str = "default"
    intent: str = ""
    forest_release_id: Optional[str] = None
    soil_checkpoint: Optional[str] = None
    prompt_context_hash: Optional[str] = None
    selected_skill_revision_id: Optional[str] = None
    decision_trace_ref: Optional[str] = None
    result_ref: Optional[str] = None
    status: RunStatus = RunStatus.RUNNING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class RunNodeReference(BaseModel):
    """Run 引用的节点修订"""
    run_id: str
    revision_id: str
    rank: int = 0
    score: float = 0.0
    usage_type: str = "retrieved"


class RunEdgeReference(BaseModel):
    """Run 引用的边修订"""
    run_id: str
    revision_id: str


class ActionResult(BaseModel):
    """动作执行结果"""
    run_id: str
    skill_revision_id: str
    input_payload: Optional[Dict[str, Any]] = None
    input_hash: str = ""
    output_ref: str = ""
    status: str = "completed"
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
