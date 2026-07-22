from quart import Blueprint, jsonify

health_bp = Blueprint("health", __name__, url_prefix="/api/v1")


@health_bp.route("/health", methods=["GET"])
async def health_check():
    """健康检查端点"""
    return jsonify({"status": "ok", "service": "yggdrasil"}), 200


__all__ = ["health_bp"]
