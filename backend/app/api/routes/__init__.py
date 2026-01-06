"""API route modules."""

from app.api.routes.backtests import router as backtests_router
from app.api.routes.health import router as health_router
from app.api.routes.signal import router as signal_router
from app.api.routes.stocks import router as stocks_router
from app.api.routes.strategies import router as strategies_router

__all__ = [
    "backtests_router",
    "health_router",
    "signal_router",
    "stocks_router",
    "strategies_router",
]
