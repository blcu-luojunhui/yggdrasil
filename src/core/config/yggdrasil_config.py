from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .database.mysql_config import YggdrasilMySQLConfig
from .observability.log_config import LogConfig
from .observability.alert_config import AlertConfig


class YggdrasilConfig(BaseSettings):
    """Yggdrasil 全局配置"""

    # 服务配置
    host: str = Field(default="0.0.0.0", description="服务监听地址")
    port: int = Field(default=6061, description="服务监听端口")
    debug: bool = Field(default=False, description="调试模式")

    # 数据库配置
    db: YggdrasilMySQLConfig = Field(default_factory=YggdrasilMySQLConfig)

    # 日志配置
    log: LogConfig = Field(default_factory=LogConfig)

    # 告警配置
    alert: AlertConfig = Field(default_factory=AlertConfig)

    # LLM 嵌入配置
    llm_provider: str = Field(default="openai", description="LLM 提供商")
    llm_base_url: str = Field(default="https://api.openai.com/v1", description="API 基础地址")
    llm_api_key: str = Field(default="", description="API Key")
    llm_model: str = Field(default="text-embedding-3-small", description="嵌入模型")
    llm_embedding_dim: int = Field(default=1536, description="嵌入维度")

    # 检索配置
    retrieval_max_nodes: int = Field(default=50, description="检索返回最大节点数")
    retrieval_max_depth: int = Field(default=2, description="BFS 最大深度")
    retrieval_strength_threshold: float = Field(default=0.2, description="强度阈值，低于此值不返回")

    # 进化配置
    evolution_step_strength: float = Field(default=0.1, description="强度更新步长")
    evolution_decay_factor: float = Field(default=0.95, description="冬季衰减系数")
    evolution_pollution_threshold: float = Field(default=0.3, description="污染阈值，超过触发自愈")

    # 巡检配置（cron 表达式，UTC）
    inspection_cron: str = Field(default="0 0 * * *", description="巡检任务 cron 表达式")

    model_config = SettingsConfigDict(
        env_prefix="YGGDRASIL_",
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )
