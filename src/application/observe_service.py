"""Observation 服务 — 只读视图模型，给前端森林观测器提供数据契约"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

from src.core.yggdrasil.ports.repositories import (
    RevisionRepository,
    RingRepository,
    RunRepository,
    SoilRepository,
    TreeRepository,
)

logger = logging.getLogger(__name__)


# ── View Models（前端消费，不暴露内部表结构）──


@dataclass
class ForestScene:
    """森林全景"""
    release_id: str = ""
    as_of: str = ""
    trees: List[dict] = field(default_factory=list)
    soil_summary: dict = field(default_factory=dict)
    active_run_count: int = 0
    truncated: bool = False


@dataclass
class TreeScene:
    """单棵树场景"""
    tree: Optional[dict] = None
    canopy: dict = field(default_factory=dict)
    trunk: dict = field(default_factory=dict)
    branches: List[dict] = field(default_factory=list)
    leaves: List[dict] = field(default_factory=list)
    fruits: List[dict] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    as_of: str = ""
    ring_id: str = ""


@dataclass
class SoilScene:
    """土地剖面"""
    layers: List[dict] = field(default_factory=list)
    events: List[dict] = field(default_factory=list)
    checkpoints: List[int] = field(default_factory=list)
    as_of: str = ""
    truncated: bool = False


@dataclass
class RunScene:
    """Run 复盘"""
    steps: List[dict] = field(default_factory=list)
    references: List[dict] = field(default_factory=list)
    path: List[dict] = field(default_factory=list)
    evaluation: Optional[dict] = None
    as_of: str = ""


@dataclass
class RingDiff:
    """Ring 对比"""
    base_ring: dict = field(default_factory=dict)
    target_ring: dict = field(default_factory=dict)
    changes: List[dict] = field(default_factory=list)
    quality_delta: dict = field(default_factory=dict)


class ObserveService:
    """观察服务 — 纯只读，不修改任何数据"""

    def __init__(
        self,
        tree_repo: TreeRepository,
        revision_repo: RevisionRepository,
        ring_repo: RingRepository,
        soil_repo: SoilRepository,
        run_repo: RunRepository,
    ):
        self._tree_repo = tree_repo
        self._revision_repo = revision_repo
        self._ring_repo = ring_repo
        self._soil_repo = soil_repo
        self._run_repo = run_repo

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    async def get_forest(self, release_id: str = "") -> ForestScene:
        """获取森林全景"""
        trees = await self._tree_repo.list()
        tree_scenes = []
        for t in trees:
            active_ring_id = t.active_ring_id
            ring_info = {}
            if active_ring_id:
                ring = await self._ring_repo.get(active_ring_id)
                if ring:
                    ring_info = {
                        "ring_id": ring.get("ring_id", ""),
                        "sequence": ring.get("sequence", 0),
                        "lifecycle": ring.get("lifecycle_status", ""),
                        "health": ring.get("health_status", ""),
                    }
            # 验证树有 active revisions（轻量检查）
            await self._revision_repo.list_all_active(tree_id=t.tree_id, limit=1)
            tree_scenes.append({
                "tree_id": t.tree_id,
                "name": t.name,
                "bounded_context": t.bounded_context,
                "owner": t.owner,
                "status": t.status,
                "active_ring": ring_info,
                "access_policy": t.access_policy,
            })

        # Soil summary
        events = await self._soil_repo.list_after_checkpoint(0, limit=100)
        soil_summary = {
            "total_events": len(events),
            "latest_checkpoint": max((e.checkpoint for e in events), default=0),
        }

        # Active runs
        running = await self._run_repo.list_by_status("running", limit=20)

        return ForestScene(
            release_id=release_id,
            as_of=self._now(),
            trees=tree_scenes,
            soil_summary=soil_summary,
            active_run_count=len(running),
        )

    async def get_tree(
        self, tree_id: str, ring_id: str = ""
    ) -> Optional[TreeScene]:
        """获取单棵树场景"""
        tree = await self._tree_repo.get(tree_id)
        if not tree:
            return None

        ring_id = ring_id or tree.active_ring_id or ""
        ring_info = {}
        if ring_id:
            r = await self._ring_repo.get(ring_id)
            if r:
                ring_info = {
                    "ring_id": r.get("ring_id", ""),
                    "sequence": r.get("sequence", 0),
                    "lifecycle": r.get("lifecycle_status", ""),
                    "health": r.get("health_status", ""),
                }

        # 获取 active revisions
        nodes = await self._revision_repo.list_all_active(tree_id=tree_id, limit=500)
        edges = await self._revision_repo.list_edges_for_ring(ring_id) if ring_id else []

        # 按角色分类
        by_role: Dict[str, list] = {}
        for n in nodes:
            by_role.setdefault(n.role, []).append(n)

        leaves = []
        for n in nodes:
            leaves.append({
                "revision_id": n.revision_id,
                "node_id": n.node_id,
                "role": n.role,
                "title": n.title,
                "summary": n.summary,
                "status": n.status.value if hasattr(n.status, "value") else str(n.status),
                "utility": n.utility,
                "confidence": n.confidence,
                "freshness": n.freshness,
                "risk": n.risk,
                "evidence_count": len(n.evidence_refs),
                "valid_from": n.valid_from.isoformat() if n.valid_from else None,
                "valid_until": n.valid_until.isoformat() if n.valid_until else None,
            })

        branches = []
        for e in edges:
            branches.append({
                "edge_id": e.edge_id,
                "revision_id": e.revision_id,
                "source_node_id": e.source_node_id,
                "target_node_id": e.target_node_id,
                "relation": e.relation,
                "weight": e.weight,
                "confidence": e.confidence,
                "status": e.status.value if hasattr(e.status, "value") else str(e.status),
            })

        # 统计
        canopy = {
            "total_revisions": len(nodes),
            "by_role": {r: len(v) for r, v in by_role.items()},
        }
        trunk = {
            "tree_id": tree.tree_id,
            "name": tree.name,
            "bounded_context": tree.bounded_context,
            "ring": ring_info,
        }
        metrics = {
            "avg_confidence": sum(n.confidence for n in nodes) / len(nodes) if nodes else 0,
            "avg_utility": sum(n.utility for n in nodes) / len(nodes) if nodes else 0,
            "avg_risk": sum(n.risk for n in nodes) / len(nodes) if nodes else 0,
            "total_edges": len(edges),
        }

        return TreeScene(
            tree={
                "tree_id": tree.tree_id,
                "name": tree.name,
                "tenant_id": tree.tenant_id,
                "bounded_context": tree.bounded_context,
            },
            canopy=canopy,
            trunk=trunk,
            branches=branches,
            leaves=leaves,
            fruits=[],
            metrics=metrics,
            as_of=self._now(),
            ring_id=ring_id,
        )

    async def get_tree_graph(
        self, tree_id: str, ring_id: str = "", role: str = "", status: str = ""
    ) -> dict:
        """获取树的可视化图数据（节点+边）"""
        scene = await self.get_tree(tree_id, ring_id)
        if not scene:
            return {"nodes": [], "edges": [], "as_of": self._now()}

        # 过滤
        leaves = scene.leaves
        if role:
            leaves = [leaf for leaf in leaves if leaf["role"] == role]
        if status:
            leaves = [leaf for leaf in leaves if leaf["status"] == status]

        return {
            "nodes": leaves,
            "edges": scene.branches,
            "as_of": self._now(),
            "ring_id": scene.ring_id,
        }

    async def get_soil_events(
        self,
        after: str = "",
        before: str = "",
        event_type: str = "",
        limit: int = 100,
    ) -> SoilScene:
        """获取土壤事件流"""
        checkpoint = 0
        events = await self._soil_repo.list_after_checkpoint(checkpoint, limit=limit)

        result_events = []
        for e in events:
            evt = {
                "event_id": e.event_id,
                "event_type": e.event_type,
                "tenant_id": e.tenant_id,
                "actor_id": e.actor_id,
                "subject_id": e.subject_id,
                "source_type": e.source_type,
                "source_ref": e.source_ref,
                "correlation_id": e.correlation_id,
                "observed_at": e.observed_at.isoformat() if e.observed_at else None,
                "ingested_at": e.ingested_at.isoformat() if e.ingested_at else None,
                "trust_level": e.trust_level,
                "integrity_hash": e.integrity_hash,
                "checkpoint": e.checkpoint,
                "contamination_status": e.contamination_status,
                "idempotency_key": e.idempotency_key,
            }
            # 事件类型过滤
            if event_type and e.event_type != event_type:
                continue
            # 时间过滤
            if after and e.observed_at and e.observed_at.isoformat() <= after:
                continue
            if before and e.observed_at and e.observed_at.isoformat() >= before:
                continue
            result_events.append(evt)

        # 时间过滤后可能截断
        truncated = len(result_events) < len(events)

        return SoilScene(
            layers=[
                {"name": "air", "label": "Agent interactions"},
                {"name": "topsoil", "label": "Observations & Evidence"},
                {"name": "common", "label": "Shared facts"},
                {"name": "bedrock", "label": "Immutable audit trail"},
            ],
            events=result_events,
            checkpoints=[e.checkpoint for e in events],
            as_of=self._now(),
            truncated=truncated,
        )

    async def get_run(self, run_id: str) -> Optional[RunScene]:
        """获取 Run 复盘"""
        run = await self._run_repo.get(run_id)
        if not run:
            return None

        steps = [
            {
                "step": "intent",
                "label": "Intent",
                "detail": run.intent,
                "started_at": run.started_at.isoformat() if run.started_at else None,
            },
            {
                "step": "status",
                "label": "Status",
                "detail": run.status.value if hasattr(run.status, "value") else str(run.status),
                "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            },
        ]

        if run.forest_release_id:
            steps.append({
                "step": "forest_router",
                "label": "Forest Release",
                "detail": run.forest_release_id,
            })

        if run.selected_skill_revision_id:
            steps.append({
                "step": "skill",
                "label": "Selected Skill",
                "detail": run.selected_skill_revision_id,
            })

        if run.prompt_context_hash:
            steps.append({
                "step": "context",
                "label": "Retrieved Context",
                "detail": f"hash: {run.prompt_context_hash[:16]}...",
            })

        if run.result_ref:
            steps.append({
                "step": "result",
                "label": "Result",
                "detail": run.result_ref,
            })

        node_refs = await self._run_repo.list_node_references(run_id)
        edge_refs = await self._run_repo.list_edge_references(run_id)
        action_results = await self._run_repo.list_action_results(run_id)

        references = [
            {"kind": "node", **ref} for ref in node_refs
        ] + [
            {"kind": "edge", **ref} for ref in edge_refs
        ]
        for action in action_results:
            steps.append({
                "step": "action",
                "label": "Skill Action",
                "detail": action.get("skill_revision_id", ""),
                "status": action.get("status", ""),
                "output_ref": action.get("output_ref", ""),
                "started_at": action.get("started_at").isoformat()
                if action.get("started_at") else None,
                "completed_at": action.get("completed_at").isoformat()
                if action.get("completed_at") else None,
            })

        return RunScene(
            steps=steps,
            references=references,
            path=[],
            evaluation=None,
            as_of=self._now(),
        )

    async def get_ring_diff(self, ring_id: str, against: str = "") -> Optional[RingDiff]:
        """获取 Ring 对比"""
        ring = await self._ring_repo.get(ring_id)
        if not ring:
            return None

        base_ring_data = {
            "ring_id": ring.get("ring_id", ""),
            "sequence": ring.get("sequence", 0),
            "lifecycle": ring.get("lifecycle_status", ""),
            "health": ring.get("health_status", ""),
            "sealed_at": str(ring.get("sealed_at", "")),
        }

        target_ring_data = dict(base_ring_data)
        changes: List[dict] = []
        quality_delta: dict = {}

        if against:
            against_ring = await self._ring_repo.get(against)
            if against_ring:
                target_ring_data = {
                    "ring_id": against_ring.get("ring_id", ""),
                    "sequence": against_ring.get("sequence", 0),
                    "lifecycle": against_ring.get("lifecycle_status", ""),
                    "health": against_ring.get("health_status", ""),
                    "sealed_at": str(against_ring.get("sealed_at", "")),
                }
                # 比较 node mappings
                base_mappings = await self._ring_repo.get_node_mappings(ring_id)
                against_mappings = await self._ring_repo.get_node_mappings(against)

                base_nodes = set(base_mappings.keys())
                against_nodes = set(against_mappings.keys())

                added_nodes = base_nodes - against_nodes
                removed_nodes = against_nodes - base_nodes
                unchanged_nodes = base_nodes & against_nodes

                for nid in added_nodes:
                    changes.append({"type": "added", "node_id": nid, "revision_id": base_mappings[nid]})
                for nid in removed_nodes:
                    changes.append({"type": "removed", "node_id": nid, "revision_id": against_mappings[nid]})
                for nid in unchanged_nodes:
                    if base_mappings[nid] != against_mappings[nid]:
                        changes.append({
                            "type": "modified",
                            "node_id": nid,
                            "old_revision_id": against_mappings[nid],
                            "new_revision_id": base_mappings[nid],
                        })
                    else:
                        changes.append({"type": "unchanged", "node_id": nid, "revision_id": base_mappings[nid]})

                quality_delta = {
                    "base_active_count": len(base_nodes),
                    "against_active_count": len(against_nodes),
                    "added": len(added_nodes),
                    "removed": len(removed_nodes),
                    "modified": sum(1 for c in changes if c["type"] == "modified"),
            }

        return RingDiff(
            base_ring=base_ring_data,
            target_ring=target_ring_data,
            changes=changes,
            quality_delta=quality_delta,
        )

    async def search(self, q: str = "", scope: str = "") -> dict:
        """全局搜索 — 按类型分组返回"""
        if not q:
            return {"forest": [], "cognitive": [], "soil": [], "run": [], "ring": [], "as_of": self._now()}

        q_lower = q.lower()
        results: dict = {
            "forest": [],
            "cognitive": [],
            "soil": [],
            "run": [],
            "ring": [],
            "as_of": self._now(),
        }

        # 搜索树
        if scope in ("", "forest"):
            trees = await self._tree_repo.list()
            for t in trees:
                if q_lower in t.name.lower() or q_lower in (t.bounded_context or "").lower():
                    results["forest"].append({
                        "tree_id": t.tree_id,
                        "name": t.name,
                        "bounded_context": t.bounded_context,
                        "active_ring_id": t.active_ring_id,
                        "status": t.status,
                    })

        return results
