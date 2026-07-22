import logging
from quart_cors import cors
from quart import Quart

from src.core.bootstrap import AppContext
from src.core.dependency import ServerContainer
from src.api.v1.routes import api_routes
from src.api.middleware import (
    TraceMiddleware,
    ErrorHandlerMiddleware,
    RequestLoggerMiddleware,
)
from src.infra.observability import TraceIdFilter

# 配置日志格式
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(trace_id)s] [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

trace_filter = TraceIdFilter()
for handler in logging.root.handlers:
    handler.addFilter(trace_filter)

app = Quart(__name__)
app = cors(app, allow_origin="*")
app.config["ACCEPTING_REQUESTS"] = True
app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024

# 注册中间件
TraceMiddleware(app)
ErrorHandlerMiddleware(app)
RequestLoggerMiddleware(app)

server_container = ServerContainer()
ctx = AppContext(server_container)

config = server_container.config()
log_service = server_container.log_service()
duckdb_pool = server_container.duckdb_pool()
yggdrasil_engine = server_container.yggdrasil_engine()

routes = api_routes(config, log_service, duckdb_pool, yggdrasil_engine)
app.register_blueprint(routes)


@app.before_serving
async def startup():
    logging.info("Starting Yggdrasil...")
    await ctx.start_up()
    logging.info("Yggdrasil started successfully")


@app.after_serving
async def shutdown():
    logging.info("Shutting down Yggdrasil...")
    app.config["ACCEPTING_REQUESTS"] = False
    await ctx.shutdown()
    logging.info("Yggdrasil shutdown complete")