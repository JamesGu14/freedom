from fastapi import APIRouter

from app.api.routes import (
    backtests_router,
    health_router,
    signal_router,
    stocks_router,
    strategies_router,
)

router = APIRouter()
router.include_router(health_router, tags=["health"])
router.include_router(stocks_router, tags=["stocks"])
router.include_router(strategies_router, tags=["strategies"])
router.include_router(signal_router, tags=["signal"])
router.include_router(backtests_router, tags=["backtests"])
