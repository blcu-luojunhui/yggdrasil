"""认知模型：Tree、NodeRevision、EdgeRevision、Ring、RetrievalScope"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ── 状态枚举 ──


class NodeStatus(str, Enum):
    CANDIDATE = "candidate"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"
    QUARANTINED = "quarantined"


class RingLifecycle(str, Enum):
    GROWING = "growing"
    EVALUATING = "evaluating"
    SEALED = "sealed"
    ARCHIVED = "archived"


class RingHealth(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    QUARANTINED = "quarantined"
    SUPERSEDED = "superseded"


class EventType(str, Enum):
    OBSERVATION = "observation"
    CLAIM = "claim"
    EVIDENCE = "evidence"
    DECISION = "decision"
    ACTION_RESULT = "action_result"
    EVALUATION = "evaluation"


class RunStatus(str, Enum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ── Tree ──


class TreeManifest(BaseModel):
    """树清单"""
    tree_id: str
    tenant_id: str = "default"
    name: str
    bounded_context: str = ""
    owner: str = ""
    ontology_version: str = "1"
    active_ring_id: Optional[str] = None
    capabilities: List[str] = Field(default_factory=list)
    access_policy: str = "default"
    retrieval_policy: str = "default"
    status: str = "active"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ── NodeRevision ──


class NodeRevision(BaseModel):
    """节点修订（不可变）"""
    revision_id: str
    node_id: str
    tree_id: str
    parent_revision_id: Optional[str] = None
    role: str = "fact"
    title: str = ""
    summary: str = ""
    payload: Optional[Dict[str, Any]] = None
    status: NodeStatus = NodeStatus.CANDIDATE
    utility: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    freshness: float = Field(default=0.5, ge=0.0, le=1.0)
    risk: float = Field(default=0.0, ge=0.0, le=1.0)
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None
    evidence_refs: List[str] = Field(default_factory=list)
    change_reason: str = ""
    author_type: str = "system"
    author_id: str = ""
    content_hash: str = ""
    created_at: Optional[datetime] = None


# ── EdgeRevision ──


class EdgeRevision(BaseModel):
    """边修订（不可变）"""
    revision_id: str
    edge_id: str
    tree_id: str
    parent_revision_id: Optional[str] = None
    source_node_id: str
    target_node_id: str
    relation: str = "enables"
    weight: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    applicability: float = Field(default=1.0, ge=0.0, le=1.0)
    propagation_policy: str = "default"
    evidence_refs: List[str] = Field(default_factory=list)
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None
    status: NodeStatus = NodeStatus.CANDIDATE
    created_at: Optional[datetime] = None


# ── Retrieval ──


class RetrievalScope(BaseModel):
    """检索范围"""
    tree_ids: List[str] = Field(default_factory=list)
    ring_ids: Dict[str, str] = Field(default_factory=dict)  # tree_id -> ring_id
    tenant_id: str = "default"
    valid_at: Optional[datetime] = None
    max_nodes: int = 50
    max_depth: int = 1


class VersionedContext(BaseModel):
    """版本化检索上下文"""
    nodes: List[NodeRevision] = Field(default_factory=list)
    edges: List[EdgeRevision] = Field(default_factory=list)
    references: List[Dict[str, Any]] = Field(default_factory=list)
    total_tokens: int = 0
    markdown: str = ""
    ring_ids: Dict[str, str] = Field(default_factory=dict)

    def to_markdown(self) -> str:
        return self.markdown
