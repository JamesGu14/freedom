"""Quant engine package."""

from app.quant.base import MultiFactorV1Strategy, StrategyContext, StrategyProtocol
from app.quant.engine import BacktestRunConfig, BacktestEngine, run_backtest_with_guard
from app.quant.registry import list_registered_strategies, load_strategy

__all__ = [
    "BacktestRunConfig",
    "BacktestEngine",
    "MultiFactorV1Strategy",
    "StrategyContext",
    "StrategyProtocol",
    "list_registered_strategies",
    "load_strategy",
    "run_backtest_with_guard",
]

