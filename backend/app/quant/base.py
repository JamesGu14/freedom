from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import pandas as pd

from app.quant.factors_stock import build_stock_factor_scores


@dataclass(slots=True)
class StrategyContext:
    trade_date: str
    frame: pd.DataFrame
    market_regime: str
    market_exposure: float
    params: dict[str, Any]


class StrategyProtocol(Protocol):
    key: str
    name: str

    def score(self, context: StrategyContext) -> pd.DataFrame:
        ...


class MultiFactorV1Strategy:
    key = "multifactor_v1"
    name = "多因子趋势增强V1"

    def score(self, context: StrategyContext) -> pd.DataFrame:
        return build_stock_factor_scores(context.frame)

