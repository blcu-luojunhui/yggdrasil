from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AlertConfig(BaseSettings):
    """告警配置"""

    queue_size: int = Field(default=1000, description="告警队列大小")

    model_config = SettingsConfigDict(
        env_prefix="YGGDRASIL_ALERT_", env_file=".env", case_sensitive=False, extra="ignore"
    )
