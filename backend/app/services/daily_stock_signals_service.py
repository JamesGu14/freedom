from __future__ import annotations

import datetime as dt
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
            "user_state": s.get("user_state"),
        }
        for s in stocks
    ]
    return doc


def _sort_stocks_by_state(stocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        stocks,
        key=lambda s: (0 if s.get("user_state") == "acknowledged" else 1, -s.get("weighted_score", 0)),
    )


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

    buy_resonance: list[dict[str, Any]] = [group for group in resonance_groups if group.get("signal_side") == "buy"]
    sell_resonance: list[dict[str, Any]] = [group for group in resonance_groups if group.get("signal_side") == "sell"]

    for group in buy_resonance:
        group["stocks"] = _sort_stocks_by_state(group.get("stocks", []))
    for group in sell_resonance:
        group["stocks"] = _sort_stocks_by_state(group.get("stocks", []))

    result = {
        "trade_date": selected_trade_date,
        "buy_signals": [group for group in signal_groups if group.get("signal_side") == "buy"],
        "sell_signals": [group for group in signal_groups if group.get("signal_side") == "sell"],
        "buy_resonance": buy_resonance,
        "sell_resonance": sell_resonance,
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
                    "user_state": stock.get("user_state"),
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


def get_signal_statistics(*, trade_date: str | None = None) -> dict[str, Any]:
    selected_date = trade_date or next(iter(list_daily_stock_signal_dates(limit=1)), None)
    if not selected_date:
        return {"trade_date": None, "panels": []}

    cache_key = f"signals:statistics:{selected_date}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    configs = [
        {"id": "3d_2", "title": "过去3天出现≥2次强共振", "window_days": 3, "threshold": 2},
        {"id": "5d_3", "title": "过去5天出现≥3次强共振", "window_days": 5, "threshold": 3},
        {"id": "10d_5", "title": "过去10天出现≥5次强共振", "window_days": 10, "threshold": 5},
    ]

    end_dt = dt.datetime.strptime(selected_date, "%Y%m%d")
    start_dt = end_dt - dt.timedelta(days=45)
    start_date = start_dt.strftime("%Y%m%d")

    trading_days_cursor = get_collection("trade_calendar").find(
        {
            "exchange": "SSE",
            "cal_date": {"$gte": start_date, "$lte": selected_date},
            "is_open": {"$in": [1, "1"]},
        },
        {"_id": 0, "cal_date": 1},
        sort=[("cal_date", 1)],
    )
    all_trading_days = [str(doc["cal_date"]) for doc in trading_days_cursor]

    if not all_trading_days:
        return {"trade_date": selected_date, "panels": []}

    cursor = get_collection("daily_stock_pattern_resonance").find(
        {
            "trade_date": {"$in": all_trading_days},
            "signal_side": "buy",
            "resonance_level": {"$in": ["strong", "very_strong"]},
        },
        {
            "_id": 0,
            "trade_date": 1,
            "resonance_level": 1,
            "stocks.ts_code": 1,
            "stocks.name": 1,
            "stocks.industry": 1,
            "stocks.close": 1,
            "stocks.pct_chg": 1,
            "stocks.volume_ratio": 1,
        }
    )

    stock_data: dict[str, dict[str, Any]] = {}
    for doc in cursor:
        doc_trade_date = doc["trade_date"]
        resonance_level = doc.get("resonance_level", "")

        for stock in doc.get("stocks", []):
            ts_code = stock["ts_code"]

            if ts_code not in stock_data:
                stock_data[ts_code] = {
                    "ts_code": ts_code,
                    "name": stock.get("name"),
                    "industry": stock.get("industry"),
                    "close": stock.get("close"),
                    "pct_chg": stock.get("pct_chg"),
                    "volume_ratio": stock.get("volume_ratio"),
                    "resonance_dates": set(),
                    "latest_trade_date": doc_trade_date,
                    "latest_resonance_level": resonance_level,
                }

            info = stock_data[ts_code]
            info["resonance_dates"].add(doc_trade_date)

            if doc_trade_date >= info["latest_trade_date"]:
                info["latest_trade_date"] = doc_trade_date
                info["latest_resonance_level"] = resonance_level
                info["close"] = stock.get("close")
                info["pct_chg"] = stock.get("pct_chg")
                info["volume_ratio"] = stock.get("volume_ratio")

    panels = []
    for config in configs:
        window_days = config["window_days"]
        threshold = config["threshold"]

        window_trading_days = all_trading_days[-window_days:] if len(all_trading_days) >= window_days else all_trading_days
        window_set = set(window_trading_days)

        filtered_stocks = []
        for ts_code, info in stock_data.items():
            count_in_window = len(info["resonance_dates"] & window_set)

            if count_in_window >= threshold:
                filtered_stocks.append({
                    "ts_code": info["ts_code"],
                    "name": info["name"],
                    "industry": info["industry"],
                    "close": info["close"],
                    "pct_chg": info["pct_chg"],
                    "volume_ratio": info["volume_ratio"],
                    "resonance_count": count_in_window,
                    "latest_resonance_level": info["latest_resonance_level"],
                    "latest_trade_date": info["latest_trade_date"],
                })

        filtered_stocks.sort(key=lambda s: (-s["resonance_count"], s["ts_code"]))

        panels.append({
            "id": config["id"],
            "title": config["title"],
            "window_days": window_days,
            "threshold": threshold,
            "count": len(filtered_stocks),
            "stocks": filtered_stocks,
        })

    result = {"trade_date": selected_date, "panels": panels}
    cache_set(cache_key, result, ttl_seconds=86400)
    return result
