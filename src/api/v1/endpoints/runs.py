"""Run API - Agent 运行追踪"""

from quart import Blueprint, request, jsonify
from dependency_injector.wiring import inject, Provide

from src.core.dependency import ServerContainer
from src.core.yggdrasil.cognitive.models import RunStatus

runs_bp = Blueprint("runs", __name__)


@runs_bp.route("/api/v1/runs", methods=["POST"])
@inject
async def start_run(run_service=Provide[ServerContainer.run_service]):
    data = await request.get_json() or {}
    if not str(data.get("intent", "")).strip():
        return jsonify({"error": "intent is required"}), 400
    run = await run_service.start_run(
        intent=data.get("intent", ""),
        tenant_id=data.get("tenant_id", "default"),
        forest_release_id=data.get("forest_release_id"),
    )
    return jsonify(run.model_dump(mode="json")), 201


@runs_bp.route("/api/v1/runs/<run_id>", methods=["GET"])
@inject
async def get_run(run_id, run_service=Provide[ServerContainer.run_service]):
    run = await run_service.get_run(run_id)
    if not run:
        return jsonify({"error": "Run not found"}), 404
    return jsonify(run.model_dump(mode="json"))


@runs_bp.route("/api/v1/runs/<run_id>/references", methods=["POST"])
@inject
async def record_references(run_id, run_service=Provide[ServerContainer.run_service]):
    data = await request.get_json() or {}
    try:
        counts = await run_service.record_references(
            run_id,
            nodes=data.get("nodes", []),
            edges=data.get("edges", []),
        )
    except ValueError as exc:
        message = str(exc)
        return jsonify({"error": message}), 404 if message.startswith("Run not found") else 400
    return jsonify({"status": "recorded", **counts}), 201


@runs_bp.route("/api/v1/runs/<run_id>/actions", methods=["POST"])
@inject
async def record_action(run_id, run_service=Provide[ServerContainer.run_service]):
    """记录 Agent 自己执行的 Skill 结果。

    Skill 本身仍由 Agent 执行；该接口只负责把结果和输入摘要挂到 Run 上。
    """
    data = await request.get_json() or {}
    skill_revision_id = str(data.get("skill_revision_id", "")).strip()
    if not skill_revision_id:
        return jsonify({"error": "skill_revision_id is required"}), 400
    try:
        await run_service.record_action_result(
            run_id=run_id,
            skill_revision_id=skill_revision_id,
            input_payload=data.get("input_payload"),
            output_ref=data.get("output_ref", ""),
            status=data.get("status", "completed"),
        )
    except ValueError as exc:
        message = str(exc)
        return jsonify({"error": message}), 404 if message.startswith("Run not found") else 409
    return jsonify({"status": "recorded", "skill_revision_id": skill_revision_id}), 201


@runs_bp.route("/api/v1/runs/<run_id>/finish", methods=["POST"])
@inject
async def finish_run(run_id, run_service=Provide[ServerContainer.run_service]):
    data = await request.get_json() or {}
    status_str = data.get("status", "succeeded")
    try:
        status = RunStatus(status_str)
    except ValueError:
        return jsonify({"error": f"Invalid status: {status_str}"}), 400
    try:
        await run_service.finish_run(run_id, status, data.get("result_ref"))
    except ValueError as exc:
        message = str(exc)
        return jsonify({"error": message}), 404 if message.startswith("Run not found") else 409
    return jsonify({"status": "finished", "run_id": run_id, "result_ref": data.get("result_ref")})
