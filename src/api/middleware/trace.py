from contextvars import ContextVar
from quart import Quart, request

from src.infra.shared.tools import generate_agent_trace_id

# 使用 ContextVar 存储当前请求的 trace_id
trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")


def get_current_trace_id() -> str:
    """获取当前请求的 trace_id"""
    return trace_id_var.get()


class TraceMiddleware:
    """
    Trace ID 中间件

    自动为每个请求生成或提取 trace_id，并注入到 context
    """

    def __init__(self, app: Quart):
        self.app = app
        app.before_request(self.before_request)

    @staticmethod
    async def before_request():
        # 优先从 header 获取，否则生成统一格式的 trace_id
        trace_id = request.headers.get("X-Trace-ID") or generate_agent_trace_id()
        trace_id_var.set(trace_id)
        request.trace_id = trace_id


__all__ = ["TraceMiddleware", "get_current_trace_id"]
