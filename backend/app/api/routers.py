from fastapi import APIRouter, Depends

from app.api.routes import (
    auth_router,
    backtests_router,
    daily_signals_router,
    health_router,
    signal_router,
    stock_groups_router,
    stocks_router,
    strategies_router,
    users_router,
)
from app.api.deps import get_current_user

router = APIRouter()
router.include_router(health_router, tags=["health"])
router.include_router(auth_router, tags=["auth"])
router.include_router(
    users_router, tags=["users"], dependencies=[Depends(get_current_user)]
)
router.include_router(
    stocks_router, tags=["stocks"], dependencies=[Depends(get_current_user)]
)
router.include_router(
    strategies_router, tags=["strategies"], dependencies=[Depends(get_current_user)]
)
router.include_router(
    signal_router, tags=["signal"], dependencies=[Depends(get_current_user)]
)
router.include_router(
    daily_signals_router, tags=["daily_signals"], dependencies=[Depends(get_current_user)]
)
router.include_router(
    stock_groups_router, tags=["stock_groups"], dependencies=[Depends(get_current_user)]
)
router.include_router(
    backtests_router, tags=["backtests"], dependencies=[Depends(get_current_user)]
)
