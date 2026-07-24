from quart import Blueprint

from src.core.config import YggdrasilConfig
from src.core.yggdrasil import YggdrasilEngine
from src.infra.database.duckdb import DuckDBPool
from src.infra.observability import LogService

from src.api.v1.endpoints.health import health_bp
from src.api.v1.endpoints.metrics import metrics_bp
from src.api.v1.endpoints.yggdrasil import yggdrasil_bp, set_engine
from src.api.v1.endpoints.sandbox import sandbox_bp, set_sandbox_engine
from src.api.v1.endpoints.trees import trees_bp
from src.api.v1.endpoints.rings import rings_bp
from src.api.v1.endpoints.soil import soil_bp
from src.api.v1.endpoints.runs import runs_bp
from src.api.v1.endpoints.observe import observe_bp


def api_routes(
    config: YggdrasilConfig,
    log_service: LogService,
    duckdb_pool: DuckDBPool,
    yggdrasil_engine: YggdrasilEngine,
) -> Blueprint:
    # 注入引擎依赖到各个 blueprint 的模块级变量
    set_engine(yggdrasil_engine)
    set_sandbox_engine(yggdrasil_engine)

    root = Blueprint("api", __name__)
    root.register_blueprint(health_bp)
    root.register_blueprint(metrics_bp)
    root.register_blueprint(yggdrasil_bp)
    root.register_blueprint(sandbox_bp)
    # 版本化 API
    root.register_blueprint(trees_bp)
    root.register_blueprint(rings_bp)
    root.register_blueprint(soil_bp)
    root.register_blueprint(runs_bp)
    root.register_blueprint(observe_bp)
    return root


__all__ = ["api_routes"]