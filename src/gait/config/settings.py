"""Application settings from environment variables."""
from __future__ import annotations

MODULE_STATUS = "UNUSED"
# Not imported by any live code path. Config is instead read ad hoc via
# os.getenv() scattered across gait.api.main, gait.api.tasks, gait.storage,
# and gait.api.session_store — this pydantic-settings class duplicates that
# but nothing constructs or injects it. To activate: replace those os.getenv()
# call sites with Depends(get_settings) (FastAPI) / get_settings() (Celery)
# and pass the resulting Settings through instead of reading env vars directly.

from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application
    app_name: str = "Sole-Arium Gait Analysis"
    app_version: str = "0.1.0"
    environment: str = "development"
    debug: bool = False

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_prefix: str = "/api/v1"

    # Database
    database_url: str = "sqlite:///./gait.db"
    database_echo: bool = False
    database_pool_size: int = 20
    database_max_overflow: int = 40

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: Optional[str] = None

    # Storage
    storage_backend: str = "s3"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_endpoint: str = "localhost:9000"
    s3_bucket_name: str = "gait-analysis"
    s3_use_ssl: bool = False

    # Authentication
    jwt_secret_key: str = "your-secret-key-here"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60
    jwt_refresh_token_expire_days: int = 7

    # Sentry
    sentry_dsn: Optional[str] = None
    sentry_traces_sample_rate: float = 0.1

    # CORS
    cors_origins: list[str] = ["*"]
    cors_credentials: bool = True

    class Config:
        """Pydantic settings config."""
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


def get_settings() -> Settings:
    """Get application settings.

    Returns:
        Settings instance
    """
    return Settings()
