from quart import Blueprint, jsonify, request
from pydantic import BaseModel

from src.core.yggdrasil import YggdrasilEngine
from src.infra.shared import ApiResponse, ErrorCodes

sandbox_bp = Blueprint("sandbox", __name__, url_prefix="/api/v1/yggdrasil/sandbox")

_engine: YggdrasilEngine = None


def set_sandbox_engine(engine: YggdrasilEngine):
    global _engine
    _engine = engine


class ForkRequest(BaseModel):
    name: str
    created_by: str | None = None


class EvaluateRequest(BaseModel):
    success: bool
    reason: str | None = None


@sandbox_bp.route("/fork", methods=["POST"])
async def fork_sandbox():
    data = await request.get_json()
    req = ForkRequest(**data)
    try:
        branch = await _engine.fork_sandbox(req.name, req.created_by)
        return jsonify(ApiResponse.success({
            "id": branch.id, "name": branch.name,
            "parent_branch_id": branch.parent_branch_id, "status": branch.status,
        })), 200
    except Exception as e:
        return jsonify(ApiResponse.error(
            ErrorCodes.INTERNAL_ERROR, f"Fork sandbox failed: {str(e)}",
        )), 500


@sandbox_bp.route("/evaluate/<branch_id>", methods=["POST"])
async def evaluate(branch_id: str):
    data = await request.get_json()
    req = EvaluateRequest(**data)
    try:
        result = await _engine.evaluate_sandbox(branch_id, req.success, req.reason)
        return jsonify(ApiResponse.success(result)), 200
    except Exception as e:
        return jsonify(ApiResponse.error(
            ErrorCodes.INTERNAL_ERROR, f"Evaluate sandbox failed: {str(e)}",
        )), 500


@sandbox_bp.route("/list", methods=["GET"])
async def list_sandboxes():
    try:
        branches = await _engine.list_sandboxes()
        return jsonify(ApiResponse.success([
            {"id": b.id, "name": b.name, "status": b.status}
            for b in branches
        ])), 200
    except Exception as e:
        return jsonify(ApiResponse.error(
            ErrorCodes.INTERNAL_ERROR, f"List sandboxes failed: {str(e)}",
        )), 500


__all__ = ["sandbox_bp", "set_sandbox_engine"]