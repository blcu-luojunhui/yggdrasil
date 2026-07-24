"""Ring API - 年轮管理与发布"""

from quart import Blueprint, request, jsonify
from dependency_injector.wiring import inject, Provide

from src.core.dependency import ServerContainer

rings_bp = Blueprint("rings", __name__)


@rings_bp.route("/api/v1/rings/<ring_id>/seal", methods=["POST"])
@inject
async def seal_ring(ring_id, ring_service=Provide[ServerContainer.ring_service]):
    result = await ring_service.seal(ring_id)
    if not result.passed:
        return jsonify({"error": "Release gate failed", "reasons": result.reasons}), 400
    return jsonify({"status": "sealed"})


@rings_bp.route("/api/v1/rings/<ring_id>/activate", methods=["POST"])
@inject
async def activate_ring(ring_id, ring_service=Provide[ServerContainer.ring_service]):
    try:
        await ring_service.activate(ring_id)
        return jsonify({"status": "activated"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@rings_bp.route("/api/v1/trees/<tree_id>/rollback", methods=["POST"])
@inject
async def rollback_tree(tree_id, ring_service=Provide[ServerContainer.ring_service]):
    data = await request.get_json() or {}
    target_ring_id = data.get("target_ring_id")
    if not target_ring_id:
        return jsonify({"error": "target_ring_id required"}), 400
    try:
        await ring_service.rollback(tree_id, target_ring_id)
        return jsonify({"status": "rolled_back"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
