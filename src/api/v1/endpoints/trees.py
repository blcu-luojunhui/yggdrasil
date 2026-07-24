"""Tree API - 树和节点管理"""

from quart import Blueprint, request, jsonify
from dependency_injector.wiring import inject, Provide

from src.core.dependency import ServerContainer

trees_bp = Blueprint("trees", __name__)


@trees_bp.route("/api/v1/trees", methods=["POST"])
@inject
async def create_tree(tree_service=Provide[ServerContainer.tree_service]):
    data = await request.get_json()
    if not data:
        return jsonify({"error": "Empty request body"}), 400
    tree = await tree_service.create_tree(
        name=data.get("name", ""),
        bounded_context=data.get("bounded_context", ""),
        tenant_id=data.get("tenant_id", "default"),
    )
    return jsonify(tree.model_dump(mode="json")), 201


@trees_bp.route("/api/v1/trees/<tree_id>", methods=["GET"])
@inject
async def get_tree(tree_id, tree_service=Provide[ServerContainer.tree_service]):
    tree = await tree_service.get_tree(tree_id)
    if not tree:
        return jsonify({"error": "Tree not found"}), 404
    return jsonify(tree.model_dump(mode="json"))


@trees_bp.route("/api/v1/trees/<tree_id>/nodes", methods=["POST"])
@inject
async def create_node(tree_id, tree_service=Provide[ServerContainer.tree_service]):
    data = await request.get_json()
    if not data:
        return jsonify({"error": "Empty request body"}), 400
    idempotency_key = request.headers.get("Idempotency-Key", "")
    if not idempotency_key:
        return jsonify({"error": "Idempotency-Key header required"}), 400

    rev = await tree_service.create_candidate_node(
        tree_id=tree_id,
        role=data.get("role", "fact"),
        title=data.get("title", ""),
        summary=data.get("summary", ""),
        payload=data.get("payload"),
        author_id=request.headers.get("X-Actor-Id", "system"),
        change_reason=data.get("change_reason", ""),
    )
    return jsonify(rev.model_dump(mode="json")), 201


@trees_bp.route("/api/v1/trees/<tree_id>/retrieve", methods=["POST"])
@inject
async def retrieve(tree_id, retrieval_service=Provide[ServerContainer.retrieval_service],
                   tree_service=Provide[ServerContainer.tree_service]):
    data = await request.get_json() or {}
    query = data.get("query", "")
    ring_id = data.get("ring_id")

    if not ring_id:
        tree = await tree_service.get_tree(tree_id)
        if not tree:
            return jsonify({"error": "Tree not found"}), 404
        ring_id = tree.active_ring_id

    if not ring_id:
        return jsonify({"error": "No active ring"}), 400

    from src.core.yggdrasil.cognitive.models import RetrievalScope
    scope = RetrievalScope(
        tree_ids=[tree_id],
        ring_ids={tree_id: ring_id},
        tenant_id=data.get("tenant_id", "default"),
        max_nodes=data.get("max_nodes", 50),
    )
    context = await retrieval_service.retrieve(query, scope)
    return jsonify({
        "nodes": [n.model_dump(mode="json") for n in context.nodes],
        "edges": [e.model_dump(mode="json") for e in context.edges],
        "total_tokens": context.total_tokens,
        "markdown": context.markdown,
        "ring_ids": context.ring_ids,
    })
