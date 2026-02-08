from __future__ import annotations

from typing import Any


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def classify_market_regime(row: dict[str, Any] | None) -> tuple[str, float]:
    if not row:
        return "neutral", 0.7

    pct_change = _to_float(row.get("pct_change")) or 0.0
    macd_value = _to_float(row.get("macd_bfq"))
    if macd_value is None:
        macd_value = _to_float(row.get("macd"))
    macd_value = macd_value or 0.0

    if pct_change >= 1.0 and macd_value > 0:
        return "risk_on", 1.0
    if pct_change <= -1.0 and macd_value < 0:
        return "risk_off", 0.4
    return "neutral", 0.7

