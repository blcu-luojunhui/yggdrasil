import uuid
import random
import string
import hashlib
from datetime import datetime, timezone
from typing import List

from requests import RequestException
from tenacity import (
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)


def str_to_md5(strings: str) -> str:
    """字符串转 MD5"""
    original_bytes = strings.encode("utf-8")
    md5_hash = hashlib.md5()
    md5_hash.update(original_bytes)
    return md5_hash.hexdigest()


def request_retry(retry_times, min_retry_delay, max_retry_delay):
    """构建 tenacity 重试配置"""
    return dict(
        stop=stop_after_attempt(retry_times),
        wait=wait_exponential(min=min_retry_delay, max=max_retry_delay),
        retry=retry_if_exception_type((RequestException, TimeoutError)),
        reraise=True,
    )


def yield_batch(data: List, batch_size: int):
    """生成批次数据"""
    for i in range(0, len(data), batch_size):
        yield data[i : i + batch_size]


def timestamp_to_str(timestamp, string_format="%Y-%m-%d %H:%M:%S") -> str:
    """时间戳转字符串"""
    dt_object = datetime.fromtimestamp(timestamp, tz=timezone.utc).astimezone()
    return dt_object.strftime(string_format)


def generate_task_trace_id() -> str:
    """生成任务追踪 ID"""
    random_str = "".join(random.choices(string.ascii_lowercase + string.digits, k=16))
    return f"Task-{datetime.now().strftime('%Y%m%d%H%M%S')}-{random_str}"


def generate_agent_trace_id() -> str:
    """Generate a unique trace ID for agent execution"""
    return f"ygg-{uuid.uuid4().hex[:12]}"
