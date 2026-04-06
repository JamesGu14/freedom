from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np
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
        return build_stock_factor_scores(context.frame, context.params)


def _clip_score(series: pd.Series | np.ndarray) -> pd.Series:
    if isinstance(series, pd.Series):
        target = series
    else:
        target = pd.Series(series)
    return target.fillna(0.0).clip(lower=0.0, upper=100.0)


def _rank_score(series: pd.Series, *, ascending: bool) -> pd.Series:
    valid = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan)
    return valid.rank(method="average", ascending=ascending, pct=True).fillna(0.5) * 100.0


def _to_weight(value: Any, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return max(number, 0.0)


def _musecat_weights(params: dict[str, Any]) -> dict[str, float]:
    defaults = {
        "momentum": 0.35,
        "reversal": 0.20,
        "quality": 0.25,
        "liquidity": 0.20,
    }
    raw = params.get("musecat_factor_weights")
    if not isinstance(raw, dict):
        return defaults
    parsed = {key: _to_weight(raw.get(key), default) for key, default in defaults.items()}
    total = sum(parsed.values())
    if total <= 0:
        return defaults
    return {key: value / total for key, value in parsed.items()}


class MuseCatV1Strategy:
    key = "musecat_v1"
    name = "MuseCat 自适应V1"

    def score(self, context: StrategyContext) -> pd.DataFrame:
        frame = context.frame
        if frame is None or frame.empty:
            return pd.DataFrame()

        data = frame.copy()
        def _numeric_series(column: str, default: float) -> pd.Series:
            if column in data.columns:
                raw = data[column]
            else:
                raw = pd.Series(default, index=data.index, dtype=float)
            series = pd.to_numeric(raw, errors="coerce")
            if isinstance(series, pd.Series):
                series = series.reindex(data.index)
            else:
                series = pd.Series(series, index=data.index)
            return series.fillna(default)

        def _piecewise(condition: pd.Series, yes: float, no: float = 0.0) -> pd.Series:
            cond = pd.Series(condition, index=data.index).fillna(False).astype(bool)
            values = np.where(cond.to_numpy(), yes, no)
            return pd.Series(values, index=data.index, dtype=float)

        close = _numeric_series("close_qfq", float("nan"))
        ma20 = _numeric_series("ma20", float("nan"))
        ma60 = _numeric_series("ma60", float("nan"))
        pct_chg = _numeric_series("pct_chg", 0.0)
        macd = _numeric_series("macd", 0.0)
        macd_signal = _numeric_series("macd_signal", 0.0)
        macd_hist = _numeric_series("macd_hist", 0.0)
        rsi12 = _numeric_series("rsi12", 50.0)
        amount = _numeric_series("amount", float("nan"))
        turnover = _numeric_series("turnover_rate", float("nan"))
        vol_ratio = _numeric_series("volume_ratio", float("nan"))
        pe_ttm = _numeric_series("pe_ttm", float("nan"))
        pb = _numeric_series("pb", float("nan"))
        sector_strength = _numeric_series("sector_strength", 50.0)

        momentum = _clip_score(
            _rank_score(pct_chg.clip(lower=-15.0, upper=15.0), ascending=True) * 0.45
            + _piecewise((close > ma20) & (ma20 > ma60), 35.0, 8.0)
            + _piecewise(macd_hist > 0, 20.0, 6.0)
        )
        reversal = _clip_score(
            _piecewise((rsi12 >= 35) & (rsi12 <= 75), 72.0, 35.0)
            + _piecewise((pct_chg >= -6.0) & (pct_chg <= 7.0), 16.0, 6.0)
        )
        quality = _clip_score(_rank_score(pe_ttm, ascending=False) * 0.6 + _rank_score(pb, ascending=False) * 0.4)
        liquidity = _clip_score(
            _rank_score(amount, ascending=True) * 0.45
            + _rank_score(turnover, ascending=True) * 0.25
            + _rank_score(vol_ratio, ascending=True) * 0.30
        )

        weights = _musecat_weights(context.params or {})
        breakout_bonus = _to_weight((context.params or {}).get("musecat_breakout_bonus"), 5.0)
        drawdown_penalty = _to_weight((context.params or {}).get("musecat_drawdown_penalty"), 6.0)
        zero_axis_cross_bonus = _to_weight((context.params or {}).get("musecat_macd_zero_axis_cross_bonus"), 8.0)
        depth_scale = _to_weight((context.params or {}).get("musecat_macd_zero_axis_depth_scale"), 3.0)
        if depth_scale <= 0:
            depth_scale = 3.0
        composite = (
            momentum * weights["momentum"]
            + reversal * weights["reversal"]
            + quality * weights["quality"]
            + liquidity * weights["liquidity"]
        )
        total = _clip_score(composite * 0.85 + sector_strength * 0.15)
        # Quantify "golden cross below zero axis": the more negative MACD, the stronger the bonus.
        zero_axis_cross = (macd_hist > 0) & (macd < 0) & (macd_signal < 0)
        near_zero_turn = (macd_hist > 0) & ((macd < 0) | (macd_signal < 0))
        # Depth weight: 0 when macd>=0, min(-macd/depth_scale, 1) when macd<0 (e.g. -3 vs -1 => 1.0 vs 0.33)
        depth_weight = (np.maximum(-macd, 0.0) / depth_scale).clip(upper=1.0)
        total = total + zero_axis_cross_bonus * depth_weight * zero_axis_cross.astype(float)
        total = total + _piecewise(~zero_axis_cross & near_zero_turn, zero_axis_cross_bonus * 0.4, 0.0)
        total = total + _piecewise((close > ma20) & (macd_hist > 0), breakout_bonus, 0.0)
        total = total - _piecewise((close < ma20) | (rsi12 > 85) | (pct_chg > 9.5), drawdown_penalty, 0.0)
        data["momentum_score"] = momentum
        data["reversal_score"] = reversal
        data["quality_score"] = quality
        data["liquidity_score"] = liquidity
        data["macd_zero_axis_cross"] = zero_axis_cross.astype(int)
        data["total_score"] = _clip_score(total)
        return data
