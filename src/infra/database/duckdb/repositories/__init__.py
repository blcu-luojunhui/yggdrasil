"""DuckDB 仓库层实现"""

import uuid


def _uuid_v7() -> str:
    """生成 UUID v7（时间有序）"""
    u = uuid.uuid4()
    return f"{u.hex[:8]}-{u.hex[8:12]}-7{u.hex[13:16]}-{u.hex[16:20]}-{u.hex[20:]}"


# 各模块从 . 导入 _uuid_v7，因此 import 必须在函数定义之后
from .outbox import DuckDBOutboxRepository  # noqa: E402
from .rings import DuckDBRingRepository  # noqa: E402
from .runs import DuckDBEvaluationRepository, DuckDBRunRepository  # noqa: E402
from .soil import DuckDBSoilRepository  # noqa: E402
from .trees import DuckDBTreeRepository  # noqa: E402
from .revisions import DuckDBRevisionRepository  # noqa: E402

__all__ = [
    "DuckDBTreeRepository",
    "DuckDBRevisionRepository",
    "DuckDBRingRepository",
    "DuckDBSoilRepository",
    "DuckDBRunRepository",
    "DuckDBEvaluationRepository",
    "DuckDBOutboxRepository",
    "_uuid_v7",
]