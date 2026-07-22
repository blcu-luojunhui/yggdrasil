from quart import Blueprint

from src.core.config import YggdrasilConfig
from src.core.yggdrasil import YggdrasilEngine
from src.infra.database.duckdb import DuckDBPool
from src.infra.observability import LogService

from src.api.v1.endpoints.health import health_bp
from src.api.v1.endpoints.metrics import metrics_bp
from src.api.v1.endpoints.yggdrasil import yggdrasil_bp


def api_routes(
    config: YggdrasilConfig,
    log_service: LogService,
    duckdb_pool: DuckDBPool,
    yggdrasil_engine: YggdrasilEngine,
) -> Blueprint:
    """注册所有 API 路由"""
    root = Blueprint("api", __name__, url_prefix="/api")
    root.register_blueprint(health_bp)
    root.register_blueprint(metrics_bp)
    root.register_blueprint(yggdrasil_bp)
    return root


__all__ = ["api_routes"]