"""Observation API — 只读观察端点，纯数据契约"""

from quart import Blueprint, jsonify, request
from dependency_injector.wiring import inject, Provide

from src.core.dependency import ServerContainer

observe_bp = Blueprint("observe", __name__)


def _envelope(data, source: str = "active_ring", release_id: str = "", truncated: bool = False):
    """统一响应 envelope"""
    from datetime import datetime, timezone
    return jsonify({
        "data": data,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "forest_release_id": release_id,
        "source": source,
        "truncated": truncated,
    })


@observe_bp.route("/api/v1/observe/forest", methods=["GET"])
@inject
async def observe_forest(observe_service=Provide[ServerContainer.observe_service]):
    release_id = request.args.get("release_id", "")
    scene = await observe_service.get_forest(release_id=release_id)
    result = {
        "release_id": scene.release_id,
        "trees": scene.trees,
        "soil_summary": scene.soil_summary,
        "active_run_count": scene.active_run_count,
    }
    return _envelope(result, release_id=release_id, truncated=scene.truncated)


@observe_bp.route("/api/v1/observe/trees/<tree_id>", methods=["GET"])
@inject
async def observe_tree(tree_id, observe_service=Provide[ServerContainer.observe_service]):
    ring_id = request.args.get("ring_id", "")
    scene = await observe_service.get_tree(tree_id, ring_id=ring_id)
    if not scene:
        return jsonify({"error": "Tree not found", "code": "NOT_FOUND"}), 404
    result = {
        "tree": scene.tree,
        "canopy": scene.canopy,
        "trunk": scene.trunk,
        "branches": scene.branches,
        "leaves": scene.leaves,
        "fruits": scene.fruits,
        "metrics": scene.metrics,
        "ring_id": scene.ring_id,
    }
    return _envelope(result)


@observe_bp.route("/api/v1/observe/trees/<tree_id>/graph", methods=["GET"])
@inject
async def observe_tree_graph(tree_id, observe_service=Provide[ServerContainer.observe_service]):
    ring_id = request.args.get("ring_id", "")
    role = request.args.get("role", "")
    status = request.args.get("status", "")
    result = await observe_service.get_tree_graph(tree_id, ring_id=ring_id, role=role, status=status)
    return _envelope(result)


@observe_bp.route("/api/v1/observe/soil/events", methods=["GET"])
@inject
async def observe_soil_events(observe_service=Provide[ServerContainer.observe_service]):
    after = request.args.get("after", "")
    before = request.args.get("before", "")
    event_type = request.args.get("event_type", "")
    limit = int(request.args.get("limit", "100"))
    scene = await observe_service.get_soil_events(
        after=after, before=before, event_type=event_type, limit=limit,
    )
    result = {
        "layers": scene.layers,
        "events": scene.events,
        "checkpoints": scene.checkpoints,
    }
    return _envelope(result, truncated=scene.truncated)


@observe_bp.route("/api/v1/observe/runs/<run_id>", methods=["GET"])
@inject
async def observe_run(run_id, observe_service=Provide[ServerContainer.observe_service]):
    scene = await observe_service.get_run(run_id)
    if not scene:
        return jsonify({"error": "Run not found", "code": "NOT_FOUND"}), 404
    result = {
        "steps": scene.steps,
        "references": scene.references,
        "path": scene.path,
        "evaluation": scene.evaluation,
    }
    return _envelope(result)


@observe_bp.route("/api/v1/observe/rings/<ring_id>/diff", methods=["GET"])
@inject
async def observe_ring_diff(ring_id, observe_service=Provide[ServerContainer.observe_service]):
    against = request.args.get("against", "")
    diff = await observe_service.get_ring_diff(ring_id, against=against)
    if not diff:
        return jsonify({"error": "Ring not found", "code": "NOT_FOUND"}), 404
    result = {
        "base_ring": diff.base_ring,
        "target_ring": diff.target_ring,
        "changes": diff.changes,
        "quality_delta": diff.quality_delta,
    }
    return _envelope(result)


@observe_bp.route("/api/v1/observe/search", methods=["GET"])
@inject
async def observe_search(observe_service=Provide[ServerContainer.observe_service]):
    q = request.args.get("q", "")
    scope = request.args.get("scope", "")
    result = await observe_service.search(q=q, scope=scope)
    return _envelope(result)
