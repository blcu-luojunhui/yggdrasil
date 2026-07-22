import logging

from src.api.middleware.trace import get_current_trace_id


class TraceIdFilter(logging.Filter):
    """为所有日志记录自动注入 trace_id"""

    def filter(self, record: logging.LogRecord) -> bool:
        trace_id = get_current_trace_id()
        record.trace_id = trace_id if trace_id else "-"
        return True
