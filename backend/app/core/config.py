from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,  # 允许环境变量不区分大小写
    )

    app_name: str = "quant-platform"
    api_prefix: str = "/api"
    log_level: str = "INFO"
    log_dir: Path = Path("/app/logs")

    tushare_token: str | None = None
    data_dir: Path = Path("./data")
    duckdb_path: Path = Path("./data/quant.duckdb")
    redis_url: str | None = None
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ]


settings = Settings()
