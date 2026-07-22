from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LogConfig(BaseSettings):
    """日志配置"""

    level: str = Field(default="INFO", description="日志级别")
    queue_size: int = Field(default=10000, description="日志队列大小")

    model_config = SettingsConfigDict(
        env_prefix="YGGDRASIL_LOG_", env_file=".env", case_sensitive=False, extra="ignore"
    )
