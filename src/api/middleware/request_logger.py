import logging
import time
from quart import Quart, request, g

logger = logging.getLogger(__name__)


class RequestLoggerMiddleware:
    """
    请求日志中间件

    记录每个请求的方法、路径、状态码和耗时
    """

    def __init__(self, app: Quart):
        self.app = app
        app.before_request(self.before_request)
        app.after_request(self.after_request)

    @staticmethod
    async def before_request():
        g.request_start_time = time.time()

    @staticmethod
    async def after_request(response):
        duration = time.time() - getattr(g, "request_start_time", time.time())
        trace_id = getattr(request, "trace_id", "-")

        # 更新 Prometheus 指标
        # Note: metrics is handled by the container, this is just logging
        logger.info(
            f"[{trace_id}] {request.method} {request.path} "
            f"-> {response.status_code} ({duration:.3f}s)"
        )

        response.headers["X-Trace-ID"] = trace_id
        response.headers["X-Response-Time"] = f"{duration:.3f}s"

        return response


__all__ = ["RequestLoggerMiddleware"]
