"""评价模型"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel


class Evaluation(BaseModel):
    """评价记录"""
    evaluation_id: str
    run_id: str
    evaluator_type: str = "system"
    technical_success: float = 0.0
    task_success: float = 0.0
    result_quality: float = 0.0
    safety: float = 1.0
    user_feedback: Optional[str] = None
    delayed_outcome: Optional[str] = None
    attribution: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None
