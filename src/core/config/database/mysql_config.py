from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class MySQLConfig(BaseSettings):
    """数据库配置基类"""

    host: str
    port: int = 3306
    user: str
    password: str
    db: str
    charset: str = "utf8mb4"
    minsize: int = 1
    maxsize: int = 10

    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False, extra="ignore")

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if not v or len(v.strip()) == 0:
            raise ValueError("password cannot be empty")
        return v

    @field_validator("port")
    @classmethod
    def validate_port(cls, v: int) -> int:
        if not (1 <= v <= 65535):
            raise ValueError(f"port must be between 1 and 65535, got: {v}")
        return v

    @field_validator("maxsize")
    @classmethod
    def validate_pool_size(cls, v: int, info) -> int:
        minsize = info.data.get("minsize", 1)
        if v < minsize:
            raise ValueError(f"maxsize ({v}) must be >= minsize ({minsize})")
        return v

    def to_dict(self) -> dict:
        """转换为字典格式，用于兼容旧代码"""
        return {
            "host": self.host,
            "port": self.port,
            "user": self.user,
            "password": self.password,
            "db": self.db,
            "charset": self.charset,
            "minsize": self.minsize,
            "maxsize": self.maxsize,
        }


class YggdrasilMySQLConfig(MySQLConfig):
    host: str = "localhost"
    user: str = "root"
    db: str = "yggdrasil"
    password: str

    model_config = SettingsConfigDict(
        env_prefix="YGGDRASIL_DB_",
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    def async_sqlalchemy_url(self) -> str:
        """SQLAlchemy 异步 DSN（aiomysql 驱动），供 base.py 与 models 使用。"""
        from urllib.parse import quote_plus

        pw = quote_plus(self.password)
        return f"mysql+aiomysql://{self.user}:{pw}@{self.host}:{self.port}/{self.db}?charset={self.charset}"
