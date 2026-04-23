from __future__ import annotations

import logging
from typing import Any

from app.core.cache import cache_get, cache_set
from app.data.duckdb_store import list_daily
from app.data.mongo import get_collection
from app.data.mongo_daily_stock_signals import (
    get_signal_group,
    list_daily_stock_signal_dates,
    list_resonance_groups_for_date,
    list_signal_groups_for_date,
    list_signals_for_stock,
)
from app.signals.patterns.config import get_pattern_category_label, get_pattern_weight

logger = logging.getLogger(__name__)


def list_available_daily_stock_signal_dates(*, limit: int = 365) -> list[str]:
    return list_daily_stock_signal_dates(limit=limit)


def _truncate_patterns(value: Any, limit: int = 10) -> list[Any]:
    return value[:limit] if isinstance(value, list) else []


def _truncate_group_stocks(group: dict[str, Any], top_n: int) -> dict[str, Any]:
    doc = dict(group)
    stocks = (doc.get("stocks") or [])[:top_n]
    doc["stocks"] = [
        {
            "ts_code": s.get("ts_code"),
            "name": s.get("name"),
            "industry": s.get("industry"),
            "close": s.get("close"),
            "pct_chg": s.get("pct_chg"),
            "volume_ratio": s.get("volume_ratio"),
            "weighted_score": s.get("weighted_score"),
            "patterns": _truncate_patterns(s.get("patterns")),
        }
        for s in stocks
    ]
    return doc


def get_daily_stock_signals_overview(*, trade_date: str | None = None, top_n: int = 50) -> dict[str, Any]:
    selected_trade_date = trade_date or next(iter(list_daily_stock_signal_dates(limit=1)), None)
    if not selected_trade_date:
        return {
            "trade_date": None,
            "buy_signals": [],
            "sell_signals": [],
            "buy_resonance": [],
            "sell_resonance": [],
        }

    cache_key = f"signals:overview:{selected_trade_date}:{top_n}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    signal_groups = [_truncate_group_stocks(group, top_n) for group in list_signal_groups_for_date(selected_trade_date)]

    resonance_groups: list[dict[str, Any]] = []
    try:
        cursor = get_collection("daily_stock_pattern_resonance").find(
            {"trade_date": selected_trade_date}, {"_id": 0}
        ).sort([("signal_side", 1), ("resonance_level", 1)])
        resonance_groups = [_truncate_group_stocks(group, top_n) for group in cursor]
    except Exception:
        logger.warning(
            "failed to load pattern resonance groups for trade_date=%s",
            selected_trade_date,
            exc_info=True,
        )
    
    result = {
        "trade_date": selected_trade_date,
        "buy_signals": [group for group in signal_groups if group.get("signal_side") == "buy"],
        "sell_signals": [group for group in signal_groups if group.get("signal_side") == "sell"],
        "buy_resonance": [group for group in resonance_groups if group.get("signal_side") == "buy"],
        "sell_resonance": [group for group in resonance_groups if group.get("signal_side") == "sell"],
    }
    
    cache_set(cache_key, result, ttl_seconds=86400 * 7)
    return result


def get_daily_stock_signal_by_type(*, trade_date: str, signal_type: str) -> dict[str, Any] | None:
    return get_signal_group(trade_date, signal_type)


def get_stock_recent_signals(*, ts_code: str, limit_days: int = 30) -> list[dict[str, Any]]:
    cache_key = f"signals:stock:{ts_code}:{limit_days}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    signals = list_signals_for_stock(ts_code=ts_code, limit_days=limit_days)
    if not signals:
        cache_set(cache_key, [], ttl_seconds=86400 * 7)
        return []

    price_rows = list_daily(ts_code)
    if not price_rows:
        cache_set(cache_key, signals, ttl_seconds=86400 * 7)
        return signals

    closes: list[float] = []
    date_to_idx: dict[str, int] = {}
    for row in price_rows:
        d = str(row.get("trade_date", ""))
        c = row.get("close")
        if d and c is not None:
            date_to_idx[d] = len(closes)
            closes.append(float(c))

    def _forward_return(trade_date: str, n_days: int) -> float | None:
        idx = date_to_idx.get(trade_date)
        if idx is None:
            return None
        target_idx = idx + n_days
        if target_idx >= len(closes):
            return None
        base = closes[idx]
        if base == 0:
            return None
        return round((closes[target_idx] - base) / base * 100, 2)

    for entry in signals:
        td = entry.get("trade_date", "")
        entry["next_1d_pct"] = _forward_return(td, 1)
        entry["next_5d_pct"] = _forward_return(td, 5)

    cache_set(cache_key, signals, ttl_seconds=86400 * 7)
    return signals


def get_stock_pattern_details(*, ts_code: str, trade_date: str) -> dict[str, Any] | None:
    cache_key = f"signals:patterns:{ts_code}:{trade_date}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    for doc in get_collection("daily_stock_pattern_resonance").find(
        {"trade_date": trade_date},
        {"_id": 0},
    ):
        for stock in doc.get("stocks", []):
            if stock.get("ts_code") == ts_code:
                patterns = stock.get("patterns", [])
                result = {
                    "ts_code": ts_code,
                    "trade_date": trade_date,
                    "name": stock.get("name"),
                    "industry": stock.get("industry"),
                    "close": stock.get("close"),
                    "pct_chg": stock.get("pct_chg"),
                    "volume_ratio": stock.get("volume_ratio"),
                    "weighted_score": stock.get("weighted_score"),
                    "resonance_level": doc.get("resonance_level"),
                    "signal_side": doc.get("signal_side"),
                    "patterns": [
                        {
                            "pattern": p,
                            "weight": get_pattern_weight(p),
                            "category": get_pattern_category_label(p),
                        }
                        for p in patterns
                    ],
                }
                cache_set(cache_key, result, ttl_seconds=86400 * 7)
                return result
    return None
