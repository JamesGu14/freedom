from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "quant-platform"
    api_prefix: str = "/api"
    log_level: str = "INFO"
    log_dir: Path = PROJECT_ROOT / "logs"

    tushare_token: str | None = None
    data_dir: Path = PROJECT_ROOT / "data"
    duckdb_path: Path = PROJECT_ROOT / "data" / "quant.duckdb"
    redis_url: str = "redis://shared-infra-shared-redis-1:6379/0"
    mongodb_url: str = "mongodb://james:2x%23fdksma%21@localhost:27017/?authSource=admin"
    mongodb_db: str = "freedom"

    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_expires_minutes: int = 120
    refresh_token_expires_days: int = 7
    internal_api_token: str = ""
    auth_login_url: str = ""
    auth_refresh_url: str = ""
    auth_logout_url: str = ""
    auth_verify_url: str = ""
    auth_verify_timeout_seconds: float = 5.0
    auth_cookie_domain: str | None = None
    auth_cookie_secure: bool = False
    auth_cookie_samesite: str = "lax"

    cors_allow_origins: str = "http://localhost:3000"

    ai_runner_base_url: str = "http://host.docker.internal:18600"
    ai_runner_token: str = ""
    ai_runner_timeout_seconds: int = 90
    ai_runner_max_retries: int = 2

    feishu_webhook_url: str | None = None


settings = Settings()
