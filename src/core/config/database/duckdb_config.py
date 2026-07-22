from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DuckDBConfig(BaseSettings):
    """DuckDB 配置"""
    path: str = Field(default="data/yggdrasil.duckdb", description="DuckDB 文件路径")
    chroma_path: str = Field(default="data/chroma", description="ChromaDB 持久化路径")

    model_config = SettingsConfigDict(
        env_prefix="YGGDRASIL_",
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )