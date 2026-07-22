import time
from quart import Blueprint, jsonify, request
from pydantic import BaseModel, Field

from src.core.yggdrasil import YggdrasilEngine, CognitiveRole, RelationType
from src.infra.shared import ApiResponse, ErrorCodes

yggdrasil_bp = Blueprint("yggdrasil", __name__, url_prefix="/api/v1/yggdrasil")


class RetrieveRequest(BaseModel):
    query: str
    domain_path: str | None = None
    max_nodes: int | None = Field(default=None, ge=1, le=200)


class CreateNodeRequest(BaseModel):
    domain_path: str
    role: str
    title: str
    content: str | None = None


class CreateEdgeRequest(BaseModel):
    source_id: str
    target_id: str
    relation: str
    strength: float = Field(default=0.5, ge=0, le=1)
    source_origin: str | None = None


class FeedbackRequest(BaseModel):
    node_id: str | None = None
    edge_id: str | None = None
    success: bool
    step: float = Field(default=0.1, ge=0, le=1)


@yggdrasil_bp.route("/retrieve", methods=["POST"])
async def retrieve(engine: YggdrasilEngine):
    data = await request.get_json()
    req = RetrieveRequest(**data)

    try:
        context = await engine.retrieve(req.query, req.domain_path, req.max_nodes)
        return jsonify(ApiResponse.success({
            "domain": (
                {"id": context.domain.id, "full_path": context.domain.full_path}
                if context.domain else None
            ),
            "nodes": [
                {
                    "id": n.id,
                    "role": n.role.value,
                    "domain_path": n.domain_path,
                    "title": n.title,
                    "content": n.content,
                    "strength": n.strength,
                    "health": n.health,
                    "season": n.season.value,
                }
                for n in context.nodes
            ],
            "edges": [
                {
                    "id": e.id,
                    "source_id": e.source_id,
                    "target_id": e.target_id,
                    "relation": e.relation.value,
                    "strength": e.strength,
                    "evidence_count": e.evidence_count,
                }
                for e in context.edges
            ],
            "total_tokens": context.total_tokens,
            "markdown": context.to_markdown(),
            "message": context.message,
        })), 200
    except Exception as e:
        return jsonify(ApiResponse.error(
            ErrorCodes.INTERNAL_ERROR, f"Retrieval failed: {str(e)}",
        )), 500


@yggdrasil_bp.route("/retrieve/markdown", methods=["POST"])
async def retrieve_markdown(engine: YggdrasilEngine):
    data = await request.get_json()
    req = RetrieveRequest(**data)
    markdown = await engine.get_markdown_context(req.query, req.domain_path)
    return markdown, 200, {"Content-Type": "text/markdown"}


@yggdrasil_bp.route("/node", methods=["POST"])
async def create_node(engine: YggdrasilEngine):
    data = await request.get_json()
    req = CreateNodeRequest(**data)

    try:
        role = CognitiveRole(req.role)
    except ValueError:
        return jsonify(ApiResponse.error(
            ErrorCodes.VALIDATION_ERROR,
            f"Invalid role: {req.role}, must be one of {[r.value for r in CognitiveRole]}",
        )), 400

    try:
        node = await engine.create_node(
            domain_path=req.domain_path,
            role=role,
            title=req.title,
            content=req.content,
        )
        return jsonify(ApiResponse.success({
            "id": node.id,
            "role": node.role.value,
            "domain_path": node.domain_path,
            "title": node.title,
            "strength": node.strength,
            "health": node.health,
            "season": node.season.value,
        })), 200
    except Exception as e:
        return jsonify(ApiResponse.error(
            ErrorCodes.INTERNAL_ERROR, f"Create node failed: {str(e)}",
        )), 500


@yggdrasil_bp.route("/edge", methods=["POST"])
async def create_edge(engine: YggdrasilEngine):
    data = await request.get_json()
    req = CreateEdgeRequest(**data)

    try:
        relation = RelationType(req.relation)
    except ValueError:
        return jsonify(ApiResponse.error(
            ErrorCodes.VALIDATION_ERROR,
            f"Invalid relation: {req.relation}, must be one of {[r.value for r in RelationType]}",
        )), 400

    try:
        edge_id = await engine.add_edge(
            source_id=req.source_id,
            target_id=req.target_id,
            relation=relation,
            strength=req.strength,
            source_origin=req.source_origin,
        )
        return jsonify(ApiResponse.success({"id": edge_id})), 200
    except Exception as e:
        return jsonify(ApiResponse.error(
            ErrorCodes.INTERNAL_ERROR, f"Create edge failed: {str(e)}",
        )), 500


@yggdrasil_bp.route("/feedback", methods=["POST"])
async def feedback(engine: YggdrasilEngine):
    data = await request.get_json()
    req = FeedbackRequest(**data)
    trace_id = getattr(request, "trace_id", None)

    try:
        await engine.feedback(
            node_id=req.node_id,
            edge_id=req.edge_id,
            success=req.success,
            step=req.step,
            trace_id=trace_id,
        )
        return jsonify(ApiResponse.success({"success": True})), 200
    except Exception as e:
        return jsonify(ApiResponse.error(
            ErrorCodes.INTERNAL_ERROR, f"Feedback failed: {str(e)}",
        )), 500


@yggdrasil_bp.route("/domain", methods=["POST"])
async def create_domain(engine: YggdrasilEngine):
    data = await request.get_json()
    domain_name = data.get("domain_name")
    parent_path = data.get("parent_path")
    if not domain_name:
        return jsonify(ApiResponse.error(
            ErrorCodes.VALIDATION_ERROR, "domain_name is required",
        )), 400

    try:
        domain = await engine.create_domain(domain_name, parent_path)
        return jsonify(ApiResponse.success({
            "id": domain.id,
            "parent_id": domain.parent_id,
            "domain_name": domain.domain_name,
            "full_path": domain.full_path,
            "depth": domain.depth,
        })), 200
    except Exception as e:
        return jsonify(ApiResponse.error(
            ErrorCodes.INTERNAL_ERROR, f"Create domain failed: {str(e)}",
        )), 500


@yggdrasil_bp.route("/nodes", methods=["GET"])
async def list_nodes(engine: YggdrasilEngine):
    domain_path = request.args.get("domain_path")
    if not domain_path:
        return jsonify(ApiResponse.error(
            ErrorCodes.VALIDATION_ERROR, "domain_path is required",
        )), 400

    nodes = await engine.list_nodes(domain_path)
    return jsonify(ApiResponse.success([
        {
            "id": n.id,
            "role": n.role.value,
            "domain_path": n.domain_path,
            "title": n.title,
            "strength": n.strength,
            "health": n.health,
            "season": n.season.value,
        }
        for n in nodes
    ])), 200


@yggdrasil_bp.route("/node/<node_id>", methods=["GET"])
async def get_node(node_id: str, engine: YggdrasilEngine):
    node = await engine.get_node(node_id)
    if not node:
        return jsonify(ApiResponse.error(
            ErrorCodes.NOT_FOUND, f"Node {node_id} not found",
        )), 404

    return jsonify(ApiResponse.success({
        "id": node.id,
        "role": node.role.value,
        "domain_id": node.domain_id,
        "domain_path": node.domain_path,
        "title": node.title,
        "content": node.content,
        "strength": node.strength,
        "health": node.health,
        "season": node.season.value,
        "tenant_id": node.tenant_id,
        "last_accessed_at": node.last_accessed_at.isoformat() if node.last_accessed_at else None,
        "created_at": node.created_at.isoformat() if node.created_at else None,
    })), 200


__all__ = ["yggdrasil_bp"]