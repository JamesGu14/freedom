"""API route modules."""

from app.api.routes.backtests import router as backtests_router
from app.api.routes.daily_signals import router as daily_signals_router
from app.api.routes.health import router as health_router
from app.api.routes.auth import router as auth_router
from app.api.routes.citic_sectors import router as citic_sectors_router
from app.api.routes.market_index import router as market_index_router
from app.api.routes.signal import router as signal_router
from app.api.routes.sector_ranking import router as sector_ranking_router
from app.api.routes.shenwan_industry import router as shenwan_industry_router
from app.api.routes.stock_groups import router as stock_groups_router
from app.api.routes.stocks import router as stocks_router
from app.api.routes.strategies import router as strategies_router
from app.api.routes.strategy_signals import router as strategy_signals_router
from app.api.routes.users import router as users_router

__all__ = [
    "backtests_router",
    "daily_signals_router",
    "health_router",
    "auth_router",
    "citic_sectors_router",
    "market_index_router",
    "signal_router",
    "sector_ranking_router",
    "shenwan_industry_router",
    "stock_groups_router",
    "stocks_router",
    "strategies_router",
    "strategy_signals_router",
    "users_router",
]
