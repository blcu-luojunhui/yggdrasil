from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .database.duckdb_config import DuckDBConfig
from .observability.log_config import LogConfig
from .observability.alert_config import AlertConfig


class YggdrasilConfig(BaseSettings):
    """Yggdrasil 全局配置"""

    # 服务配置
    host: str = Field(default="0.0.0.0", description="服务监听地址")
    port: int = Field(default=6061, description="服务监听端口")
    debug: bool = Field(default=False, description="调试模式")

    # 数据库配置
    duckdb_path: str = Field(default="data/yggdrasil.duckdb", description="DuckDB 文件路径")
    chroma_path: str = Field(default="data/chroma", description="ChromaDB 持久化路径")

    # 日志
    log: LogConfig = Field(default_factory=LogConfig)

    # 告警
    alert: AlertConfig = Field(default_factory=AlertConfig)

    # LLM 嵌入
    llm_provider: str = Field(default="openai", description="LLM 提供商")
    llm_base_url: str = Field(default="https://api.openai.com/v1", description="API 基础地址")
    llm_api_key: str = Field(default="", description="API Key")
    llm_model: str = Field(default="text-embedding-3-small", description="嵌入模型")
    llm_embedding_dim: int = Field(default=1536, description="嵌入维度")

    # 检索
    retrieval_max_nodes: int = Field(default=50, description="检索返回最大节点数")
    retrieval_max_depth: int = Field(default=2, description="BFS 最大深度")
    retrieval_strength_threshold: float = Field(default=0.2, description="强度阈值")

    # 进化
    evolution_step_strength: float = Field(default=0.1, description="强度更新步长")
    evolution_decay_factor: float = Field(default=0.95, description="冬季衰减系数")
    evolution_pollution_threshold: float = Field(default=0.3, description="污染阈值")

    # 巡检
    inspection_cron: str = Field(default="0 0 * * *", description="巡检 cron 表达式")

    model_config = SettingsConfigDict(
        env_prefix="YGGDRASIL_",
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )