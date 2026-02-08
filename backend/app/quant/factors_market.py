from __future__ import annotations

from typing import Any


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def classify_market_regime(
    row: dict[str, Any] | None,
    *,
    recent_pct_changes: list[float] | None = None,
) -> tuple[str, float]:
    if not row:
        return "neutral", 0.7

    pct_change = _to_float(row.get("pct_change")) or 0.0
    macd_value = _to_float(row.get("macd_bfq"))
    if macd_value is None:
        macd_value = _to_float(row.get("macd"))
    macd_value = macd_value or 0.0

    history = list(recent_pct_changes or [])
    history.append(pct_change)
    recent5 = history[-5:]
    recent20 = history[-20:]
    ma5 = sum(recent5) / len(recent5) if recent5 else pct_change
    ma20 = sum(recent20) / len(recent20) if recent20 else pct_change
    up_ratio5 = (sum(1 for value in recent5 if value > 0) / len(recent5)) if recent5 else 0.5

    risk_on = (
        (ma5 >= 0.20 and ma20 >= 0.05 and up_ratio5 >= 0.60 and macd_value >= 0)
        or (ma5 >= 0.35 and ma20 >= 0.10)
    )
    risk_off = (
        (ma5 <= -0.25 and ma20 <= -0.05 and up_ratio5 <= 0.40 and macd_value <= 0)
        or (ma5 <= -0.45 and ma20 <= -0.15)
    )

    if risk_on:
        return "risk_on", 1.0
    if risk_off:
        return "risk_off", 0.4
    return "neutral", 0.7
