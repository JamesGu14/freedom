from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html

from app.api.routers import router as api_router
from app.core.config import settings
from app.core.logging import configure_logging
from app.data.duckdb_store import close_read_connection
from app.data.mongo_stock import ensure_stock_basic_indexes
from app.data.mongo_data_sync_job_run import ensure_data_sync_job_run_indexes
from app.data.mongo_strategy_job_run import ensure_strategy_job_run_indexes
from app.data.mongo_strategy_signal import ensure_strategy_signal_indexes
from app.data.mongo_agent_freedom import ensure_agent_freedom_indexes
from app.data.redis_client import close_redis_client


def create_app() -> FastAPI:
    configure_logging(settings.log_level)
    application = FastAPI(
        title=settings.app_name,
        docs_url=None,
        redoc_url=None,
        openapi_url=f"{settings.api_prefix}/openapi.json",
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[origin.strip() for origin in settings.cors_allow_origins.split(",") if origin.strip()],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(api_router, prefix=settings.api_prefix)

    @application.get(f"{settings.api_prefix}/docs", include_in_schema=False)
    def swagger_ui_html():
        # Use relative OpenAPI URL so `/freedom/api/docs` works correctly behind nginx basePath.
        return get_swagger_ui_html(
            openapi_url="openapi.json",
            title=f"{settings.app_name} - Swagger UI",
        )

    @application.get(f"{settings.api_prefix}/redoc", include_in_schema=False)
    def redoc_html():
        return get_redoc_html(
            openapi_url="openapi.json",
            title=f"{settings.app_name} - ReDoc",
        )

    @application.on_event("startup")
    def _startup() -> None:
        ensure_stock_basic_indexes()
        from app.data.mongo_users import ensure_admin_user, ensure_users_indexes
        from app.data.mongo_refresh_tokens import ensure_refresh_token_indexes
        from app.data.mongo_backtest import ensure_strategy_backtest_indexes

        ensure_users_indexes()
        ensure_refresh_token_indexes()
        ensure_strategy_backtest_indexes()
        ensure_strategy_signal_indexes()
        ensure_strategy_job_run_indexes()
        ensure_data_sync_job_run_indexes()
        ensure_agent_freedom_indexes()
        from app.data.mongo_data_sync_date import ensure_data_sync_date_indexes

        ensure_data_sync_date_indexes()
        ensure_admin_user(settings.admin_username, settings.admin_password)

    @application.on_event("shutdown")
    def _shutdown() -> None:
        close_read_connection()
        close_redis_client()

    return application


app = create_app()
