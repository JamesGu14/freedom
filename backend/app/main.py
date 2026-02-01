from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import router as api_router
from app.core.config import settings
from app.core.logging import configure_logging
from app.data.mongo_stock import ensure_stock_basic_indexes


def create_app() -> FastAPI:
    configure_logging(settings.log_level)
    application = FastAPI(title=settings.app_name)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(api_router, prefix=settings.api_prefix)

    @application.on_event("startup")
    def _startup() -> None:
        ensure_stock_basic_indexes()

    return application


app = create_app()
