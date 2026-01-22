from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import router as api_router
from app.core.config import settings
from app.core.logging import configure_logging


def create_app() -> FastAPI:
    configure_logging(settings.log_level)
    application = FastAPI(title=settings.app_name)
    
    # CORS 配置：允许前端访问
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
    )
    
    application.include_router(api_router, prefix=settings.api_prefix)
    application.add_event_handler("startup", lambda: configure_logging(settings.log_level))
    return application


app = create_app()
