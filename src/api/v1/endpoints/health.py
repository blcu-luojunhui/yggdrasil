from quart import Blueprint, jsonify

from src.core.config import YggdrasilConfig

health_bp = Blueprint("health", __name__, url_prefix="/api/v1")


@health_bp.route("/health", methods=["GET"])
async def health_check():
    """健康检查端点"""
    return jsonify({
        "status": "ok",
        "service": "yggdrasil",
    }), 200


@health_bp.route("/config", methods=["GET"])
async def get_config(config: YggdrasilConfig):
    """返回非敏感配置信息用于调试"""
    return jsonify({
        "host": config.host,
        "port": config.port,
        "debug": config.debug,
        "retrieval_max_nodes": config.retrieval_max_nodes,
        "retrieval_max_depth": config.retrieval_max_depth,
        "llm_model": config.llm_model,
        "embedding_dim": config.llm_embedding_dim,
    }), 200


__all__ = ["health_bp"]
