import time
from quart import Blueprint, jsonify, request
from pydantic import BaseModel, Field

from src.core.config import YggdrasilConfig
from src.core.yggdrasil import YggdrasilEngine, CognitiveRole, RelationType, SubtreeContext
from src.infra.observability import MetricsCollector
from src.infra.shared import ApiResponse, ErrorCodes

yggdrasil_bp = Blueprint("yggdrasil", __name__, url_prefix="/api/v1/yggdrasil")


class RetrieveRequest(BaseModel):
    query: str
    domain_path: str | None = None
    max_nodes: int | None = Field(default=None, ge=1, le=200)


class CreateNodeRequest(BaseModel):
    domain_path: str
    role: str
    node_name: str
    content: str | None = None
    description: str | None = None
    generate_embedding: bool = True


class CreateEdgeRequest(BaseModel):
    from_node: int
    to_node: int
    relation_type: str
    strength: float = Field(default=0.5, ge=0, le=1)
    source: str | None = None


class FeedbackRequest(BaseModel):
    node_id: int | None = None
    edge_id: int | None = None
    success: bool
    step: float = Field(default=0.1, ge=0, le=1)


@yggdrasil_bp.route("/retrieve", methods=["POST"])
async def retrieve(engine: YggdrasilEngine, metrics: MetricsCollector):
    """
    检索认知子树

    输入查询意图，返回相关认知节点组成的子树
    """
    start_time = time.time()
    data = await request.get_json()
    req = RetrieveRequest(**data)

    try:
        context = await engine.retrieve(req.query, req.domain_path, req.max_nodes)
        metrics.increment_request("/api/v1/yggdrasil/retrieve", "POST")
        metrics.observe_request_latency("/api/v1/yggdrasil/retrieve", time.time() - start_time)

        return jsonify(ApiResponse.success({
            "domain": {
                "id": context.domain.id,
                "full_path": context.domain.full_path,
                "season": context.domain.season.value,
            },
            "nodes": [
                {
                    "id": n.id,
                    "role": n.role.value,
                    "name": n.node_name,
                    "description": n.description,
                    "content": n.content,
                    "strength": n.strength,
                    "health": n.health,
                }
                for n in context.nodes
            ],
            "edges": [
                {
                    "id": e.id,
                    "from_node": e.from_node_id,
                    "to_node": e.to_node_id,
                    "relation_type": e.relation_type.value,
                    "strength": e.strength,
                }
                for e in context.edges
            ],
            "total_tokens": context.total_tokens,
            "markdown": context.to_markdown(),
            "message": context.message,
        })), 200
    except Exception as e:
        metrics.increment_request("/api/v1/yggdrasil/retrieve", "POST")
        metrics.observe_request_latency("/api/v1/yggdrasil/retrieve", time.time() - start_time)
        return jsonify(ApiResponse.error(
            ErrorCodes.INTERNAL_ERROR,
            f"Retrieval failed: {str(e)}",
        )), 500


@yggdrasil_bp.route("/retrieve/markdown", methods=["POST"])
async def retrieve_markdown(engine: YggdrasilEngine):
    """
    检索并直接返回 Markdown 格式，方便直接注入 prompt
    """
    data = await request.get_json()
    req = RetrieveRequest(**data)
    markdown = await engine.get_markdown_context(req.query, req.domain_path)
    return markdown, 200, {"Content-Type": "text/markdown"}


@yggdrasil_bp.route("/node", methods=["POST"])
async def create_node(engine: YggdrasilEngine):
    """创建新认知节点"""
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
            node_name=req.node_name,
            content=req.content,
            description=req.description,
            generate_embedding=req.generate_embedding,
        )
        return jsonify(ApiResponse.success({
            "id": node.id,
            "domain_id": node.domain_id,
            "role": node.role.value,
            "node_name": node.node_name,
            "strength": node.strength,
            "health": node.health,
        })), 200
    except Exception as e:
        return jsonify(ApiResponse.error(
            ErrorCodes.INTERNAL_ERROR,
            f"Create node failed: {str(e)}",
        )), 500


@yggdrasil_bp.route("/edge", methods=["POST"])
async def create_edge(engine: YggdrasilEngine):
    """创建或更新边"""
    data = await request.get_json()
    req = CreateEdgeRequest(**data)

    try:
        relation_type = RelationType(req.relation_type)
    except ValueError:
        return jsonify(ApiResponse.error(
            ErrorCodes.VALIDATION_ERROR,
            f"Invalid relation_type: {req.relation_type}, "
            f"must be one of {[r.value for r in RelationType]}",
        )), 400

    try:
        edge_id = await engine.add_edge(
            from_node=req.from_node,
            to_node=req.to_node,
            relation_type=relation_type,
            strength=req.strength,
            source=req.source,
        )
        return jsonify(ApiResponse.success({
            "id": edge_id,
        })), 200
    except Exception as e:
        return jsonify(ApiResponse.error(
            ErrorCodes.INTERNAL_ERROR,
            f"Create edge failed: {str(e)}",
        )), 500


@yggdrasil_bp.route("/feedback", methods=["POST"])
async def feedback(engine: YggdrasilEngine):
    """执行反馈，更新强度"""
    data = await request.get_json()
    req = FeedbackRequest(**data)
    trace_id = request.trace_id if hasattr(request, 'trace_id') else None

    try:
        await engine.feedback(
            node_id=req.node_id,
            edge_id=req.edge_id,
            success=req.success,
            step=req.step,
            trace_id=trace_id,
        )
        return jsonify(ApiResponse.success({
            "success": True,
        })), 200
    except Exception as e:
        return jsonify(ApiResponse.error(
            ErrorCodes.INTERNAL_ERROR,
            f"Feedback failed: {str(e)}",
        )), 500


@yggdrasil_bp.route("/domain", methods=["POST"])
async def create_domain(engine: YggdrasilEngine):
    """创建新领域"""
    data = await request.get_json()
    domain_name = data.get("domain_name")
    parent_path = data.get("parent_path")

    if not domain_name:
        return jsonify(ApiResponse.error(
            ErrorCodes.VALIDATION_ERROR,
            "domain_name is required",
        )), 400

    try:
        domain = await engine.create_domain(domain_name, parent_path)
        return jsonify(ApiResponse.success({
            "id": domain.id,
            "parent_id": domain.parent_id,
            "domain_name": domain.domain_name,
            "full_path": domain.full_path,
            "depth": domain.depth,
            "season": domain.season.value,
        })), 200
    except Exception as e:
        return jsonify(ApiResponse.error(
            ErrorCodes.INTERNAL_ERROR,
            f"Create domain failed: {str(e)}",
        )), 500


@yggdrasil_bp.route("/nodes", methods=["GET"])
async def list_nodes(engine: YggdrasilEngine):
    """列出领域下所有节点"""
    domain_path = request.args.get("domain_path")
    if not domain_path:
        return jsonify(ApiResponse.error(
            ErrorCodes.VALIDATION_ERROR,
            "domain_path query parameter is required",
        )), 400

    nodes = await engine.list_nodes(domain_path)
    return jsonify(ApiResponse.success([
        {
            "id": n.id,
            "role": n.role.value,
            "node_name": n.node_name,
            "strength": n.strength,
            "health": n.health,
        }
        for n in nodes
    ])), 200


@yggdrasil_bp.route("/node/<int:node_id>", methods=["GET"])
async def get_node(node_id: int, engine: YggdrasilEngine):
    """获取节点详情"""
    node = await engine.get_node(node_id)
    if not node:
        return jsonify(ApiResponse.error(
            ErrorCodes.NOT_FOUND,
            f"Node {node_id} not found",
        )), 404

    return jsonify(ApiResponse.success({
        "id": node.id,
        "domain_id": node.domain_id,
        "role": node.role.value,
        "node_name": node.node_name,
        "description": node.description,
        "content": node.content,
        "strength": node.strength,
        "health": node.health,
        "is_isolated": node.is_isolated,
        "last_used_at": node.last_used_at.isoformat() if node.last_used_at else None,
        "created_at": node.created_at.isoformat() if node.created_at else None,
    })), 200


__all__ = ["yggdrasil_bp"]
