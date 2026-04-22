from fastapi import APIRouter, Depends

from app.api.routes import (
    agent_required_api_router,
    agent_freedom_router,
    auth_router,
    backtests_router,
    citic_sectors_router,
    data_sync_router,
    daily_signals_router,
    daily_stock_signals_router,
    health_router,
    internal_audits_router,
    market_data_router,
    market_index_router,
    market_regime_router,
    research_router,
    signal_router,
    sector_ranking_router,
    shenwan_industry_router,
    stock_groups_router,
    stocks_router,
    strategies_router,
    strategy_signals_router,
)
from app.api.deps import get_current_user

router = APIRouter()
router.include_router(health_router, tags=["health"])
router.include_router(auth_router, tags=["auth"])
router.include_router(
    agent_required_api_router,
    tags=["agent_required_api"],
    dependencies=[Depends(get_current_user)],
)
router.include_router(
    agent_freedom_router,
    tags=["agent_freedom"],
    dependencies=[Depends(get_current_user)],
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
    sector_ranking_router,
    tags=["sector_ranking"],
    dependencies=[Depends(get_current_user)],
)
router.include_router(
    shenwan_industry_router,
    tags=["shenwan_industry"],
    dependencies=[Depends(get_current_user)],
)
router.include_router(
    citic_sectors_router,
    tags=["citic_sectors"],
    dependencies=[Depends(get_current_user)],
)
router.include_router(
    market_index_router,
    tags=["market_index"],
    dependencies=[Depends(get_current_user)],
)
router.include_router(
    daily_signals_router, tags=["daily_signals"], dependencies=[Depends(get_current_user)]
)
router.include_router(
    daily_stock_signals_router, tags=["daily_stock_signals"], dependencies=[Depends(get_current_user)]
)
router.include_router(
    strategy_signals_router,
    tags=["strategy_signals"],
    dependencies=[Depends(get_current_user)],
)
router.include_router(
    stock_groups_router, tags=["stock_groups"], dependencies=[Depends(get_current_user)]
)
router.include_router(
    backtests_router, tags=["backtests"], dependencies=[Depends(get_current_user)]
)
router.include_router(
    data_sync_router, tags=["data_sync"], dependencies=[Depends(get_current_user)]
)
router.include_router(
    internal_audits_router, tags=["internal_audits"], dependencies=[Depends(get_current_user)]
)
router.include_router(
    market_data_router, tags=["market_data"], dependencies=[Depends(get_current_user)]
)
router.include_router(
    research_router, tags=["research"], dependencies=[Depends(get_current_user)]
)
router.include_router(
    market_regime_router, tags=["market_regime"], dependencies=[Depends(get_current_user)]
)
