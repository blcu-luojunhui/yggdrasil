"""森林模型：Forest Release（多树组合发布）"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ForestRelease(BaseModel):
    """森林发布（多棵树的 Ring 组合）"""
    release_id: str
    sequence: int = 1
    status: str = "draft"
    content_hash: str = ""
    created_at: Optional[datetime] = None
    activated_at: Optional[datetime] = None


class ForestReleaseRing(BaseModel):
    """森林发布与树的 Ring 映射"""
    release_id: str
    tree_id: str
    ring_id: str
