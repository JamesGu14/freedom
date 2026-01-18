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

    tushare_token: str | None = "e14d179a9b5acda0028ea672ecb535d9541402ba5e15e31687a4439e"
    data_dir: Path = PROJECT_ROOT / "data"
    duckdb_path: Path = PROJECT_ROOT / "data" / "quant.duckdb"
    redis_url: str | None = None
    mongodb_url: str = "mongodb://james:2x%23fdksma%21@localhost:27017/?authSource=admin"
    mongodb_db: str = "freedom"


settings = Settings()
