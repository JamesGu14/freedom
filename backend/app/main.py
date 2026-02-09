from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import router as api_router
from app.core.config import settings
from app.core.logging import configure_logging
from app.data.mongo_stock import ensure_stock_basic_indexes
from app.data.mongo_strategy_job_run import ensure_strategy_job_run_indexes
from app.data.mongo_strategy_signal import ensure_strategy_signal_indexes


def create_app() -> FastAPI:
    configure_logging(settings.log_level)
    application = FastAPI(title=settings.app_name)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[origin.strip() for origin in settings.cors_allow_origins.split(",") if origin.strip()],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(api_router, prefix=settings.api_prefix)

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
        ensure_admin_user(settings.admin_username, settings.admin_password)

    return application


app = create_app()
