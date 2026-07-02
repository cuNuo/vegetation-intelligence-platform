# backend/app/settings.py
# 文件说明：应用配置模型。
# 主要职责：集中读取 Redis、数据库、MinIO、Nacos、LLM 与实例参数。
# 对外入口：Settings、settings。
# 依赖边界：只定义配置，不在导入阶段连接外部服务。

"""应用配置。"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """封装 Settings 相关状态、约束和可复用行为。"""
    app_name: str = "植被指数智能分析平台"
    data_dir: Path = Path("data")
    redis_url: str = "redis://localhost:6379/0"
    celery_always_eager: bool = True
    database_url: str | None = None
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "vegetation"
    minio_secret_key: str = "vegetation-secret"
    minio_secure: bool = False
    minio_bucket: str = "vegetation-assets"
    minio_enabled: bool = False
    openai_base_url: str | None = None
    openai_api_key: str | None = None
    openai_model: str = "gpt-4.1-mini"
    service_name: str = "vegetation-basic"
    service_host: str = "api-basic"
    service_port: int = 8000
    nacos_url: str | None = None

    model_config = SettingsConfigDict(
        env_prefix="VIP_",
        env_file=("../.env", ".env"),
        extra="ignore",
    )


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
