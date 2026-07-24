"""土壤模型：事件和证据（追加写的事实源）"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class SoilEvent(BaseModel):
    """土壤事件（追加写，不可变）"""
    event_id: str
    event_type: str
    tenant_id: str = "default"
    actor_id: str = ""
    subject_id: str = ""
    source_type: str = ""
    source_ref: str = ""
    payload: Optional[Dict[str, Any]] = None
    observed_at: Optional[datetime] = None
    ingested_at: Optional[datetime] = None
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None
    trust_level: float = Field(default=0.5, ge=0.0, le=1.0)
    integrity_hash: str = ""
    access_scope: str = "default"
    contamination_status: str = "clean"
    correlation_id: Optional[str] = None
    causation_id: Optional[str] = None
    idempotency_key: str = ""
    checkpoint: int = 0


class Evidence(BaseModel):
    """证据（大对象引用）"""
    evidence_id: str
    event_id: str
    media_type: str = "application/json"
    object_ref: str = ""
    content_hash: str = ""
    classification: str = "general"
    access_scope: str = "default"
    created_at: Optional[datetime] = None
