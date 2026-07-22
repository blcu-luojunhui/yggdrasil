from quart import Blueprint, Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

metrics_bp = Blueprint("metrics", __name__, url_prefix="/api/v1")


@metrics_bp.route("/metrics", methods=["GET"])
async def metrics():
    """Prometheus metrics 端点"""
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)


__all__ = ["metrics_bp"]
