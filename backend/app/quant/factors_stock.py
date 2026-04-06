from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


DEFAULT_FACTOR_WEIGHTS: dict[str, float] = {
    "stock_trend": 0.35,
    "sector_strength": 0.25,
    "value_quality": 0.25,
    "liquidity_stability": 0.15,
}


def _clip_series(series: pd.Series, low: float = 0.0, high: float = 100.0) -> pd.Series:
    return series.fillna(0.0).clip(lower=low, upper=high)


def _safe_rank_score(series: pd.Series, ascending: bool = True) -> pd.Series:
    valid = series.replace([np.inf, -np.inf], np.nan)
    pct = valid.rank(method="average", ascending=ascending, pct=True)
    return pct.fillna(0.5) * 100.0


def _trend_score(frame: pd.DataFrame) -> pd.Series:
    close = frame.get("close_qfq")
    ma20 = frame.get("ma20")
    ma60 = frame.get("ma60")
    macd_hist = frame.get("macd_hist")
    rsi12 = frame.get("rsi12")
    kdj_k = frame.get("kdj_k")
    kdj_d = frame.get("kdj_d")
    kdj_j = frame.get("kdj_j")
    boll_upper = frame.get("boll_upper")
    boll_middle = frame.get("boll_middle")
    boll_lower = frame.get("boll_lower")

    score = pd.Series(0.0, index=frame.index, dtype=float)
    score += np.where((close > ma20) & (ma20 > ma60), 35.0, 8.0)
    score += np.where(macd_hist > 0, 20.0, 6.0)
    score += np.where((rsi12 >= 50) & (rsi12 <= 80), 14.0, 6.0)
    score += np.where((kdj_k > kdj_d) & (kdj_j > kdj_d), 14.0, 5.0)
    score += np.where((close >= boll_middle) & (close <= boll_upper), 12.0, 4.0)
    score += np.where(close < boll_lower, -12.0, 0.0)
    score += np.where((rsi12 > 85) | (frame.get("pct_chg", 0) > 9.0), -10.0, 6.0)
    return _clip_series(score)


def _value_quality_score(frame: pd.DataFrame) -> pd.Series:
    pe_score = _safe_rank_score(frame.get("pe_ttm"), ascending=False)
    pb_score = _safe_rank_score(frame.get("pb"), ascending=False)
    return _clip_series(pe_score * 0.6 + pb_score * 0.4)


def _liquidity_stability_score(frame: pd.DataFrame) -> pd.Series:
    amount = frame.get("amount")
    turnover = frame.get("turnover_rate")
    atr = frame.get("atr")
    close = frame.get("close_qfq")
    vol_ratio = frame.get("volume_ratio")

    amount_score = _safe_rank_score(amount, ascending=True)
    turnover_score = _safe_rank_score(turnover, ascending=True)
    atr_ratio = (atr / close.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan)
    atr_score = _safe_rank_score(atr_ratio, ascending=False)
    activity = _safe_rank_score(vol_ratio, ascending=True)
    return _clip_series(amount_score * 0.35 + turnover_score * 0.25 + atr_score * 0.25 + activity * 0.15)


def _resolve_factor_weights(params: dict[str, Any] | None) -> dict[str, float]:
    if not isinstance(params, dict):
        return dict(DEFAULT_FACTOR_WEIGHTS)
    value = params.get("factor_weights")
    if not isinstance(value, dict):
        return dict(DEFAULT_FACTOR_WEIGHTS)

    parsed: dict[str, float] = {}
    for key, default_weight in DEFAULT_FACTOR_WEIGHTS.items():
        raw = value.get(key, default_weight)
        try:
            number = float(raw)
        except (TypeError, ValueError):
            number = default_weight
        parsed[key] = max(number, 0.0)

    total = sum(parsed.values())
    if total <= 0:
        return dict(DEFAULT_FACTOR_WEIGHTS)
    return {key: weight / total for key, weight in parsed.items()}


def build_stock_factor_scores(
    frame: pd.DataFrame,
    params: dict[str, Any] | None = None,
) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame()
    data = frame.copy()
    data["stock_trend"] = _trend_score(data)
    data["value_quality"] = _value_quality_score(data)
    data["liquidity_stability"] = _liquidity_stability_score(data)
    weights = _resolve_factor_weights(params)
    data["total_score"] = (
        data["stock_trend"] * weights["stock_trend"]
        + data.get("sector_strength", 50.0) * weights["sector_strength"]
        + data["value_quality"] * weights["value_quality"]
        + data["liquidity_stability"] * weights["liquidity_stability"]
    ).clip(lower=0.0, upper=100.0)
    return data
