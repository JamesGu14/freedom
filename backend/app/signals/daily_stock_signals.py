from __future__ import annotations

import datetime as dt
from typing import Any

import pandas as pd

from app.core.config import settings
from app.data.duckdb_store import get_connection
from app.data.mongo_stock import get_stock_basic_map
from app.signals.patterns.config import (
    BUY_PATTERNS,
    SELL_PATTERNS,
    calculate_weighted_score,
)
from app.signals.patterns.engine import compute_pattern_flags_for_stock


BUY_SIGNAL_TYPES = (
    "buy_ma_bullish_formation",
)

SELL_SIGNAL_TYPES = (
    "sell_ma_bearish_formation",
)

ALL_SIGNAL_TYPES = (*BUY_SIGNAL_TYPES, *SELL_SIGNAL_TYPES)
RESONANCE_LEVELS = ("normal", "strong", "very_strong")


def classify_resonance_level(signal_count: int) -> str | None:
    if signal_count >= 4:
        return "very_strong"
    if signal_count == 3:
        return "strong"
    if signal_count == 2:
        return "normal"
    return None


def classify_resonance_level_weighted(weighted_score: int) -> str | None:
    from app.signals.patterns.config import RESONANCE_THRESHOLDS
    if weighted_score >= RESONANCE_THRESHOLDS["very_strong"]:
        return "very_strong"
    if weighted_score >= RESONANCE_THRESHOLDS["strong"]:
        return "strong"
    if weighted_score >= RESONANCE_THRESHOLDS["normal"]:
        return "normal"
    return None


def _has_bullish_cross(today_fast: float, today_slow: float, prev_fast: float, prev_slow: float) -> bool:
    return today_fast > today_slow and prev_fast <= prev_slow


def _has_bearish_cross(today_fast: float, today_slow: float, prev_fast: float, prev_slow: float) -> bool:
    return today_fast < today_slow and prev_fast >= prev_slow


def compute_signal_flags_for_stock(rows: list[dict[str, Any]], *, target_date: str) -> dict[str, bool]:
    by_date = {str(row["trade_date"]): row for row in rows}
    dates = sorted(by_date)
    if target_date not in by_date:
        return {signal_type: False for signal_type in ALL_SIGNAL_TYPES}

    index = dates.index(target_date)
    if index == 0:
        return {signal_type: False for signal_type in ALL_SIGNAL_TYPES}

    today = by_date[target_date]
    prev = by_date[dates[index - 1]]
    prior_window = [by_date[date] for date in dates[max(0, index - 20) : index]]
    return _compute_signal_flags_from_context(today, prev, prior_window)


def _compute_signal_flags_from_context(
    today: dict[str, Any],
    prev: dict[str, Any],
    prior_window: list[dict[str, Any]],
) -> dict[str, bool]:
    prior_high = max((float(item["close_qfq"]) for item in prior_window), default=float("-inf"))
    prior_low = min((float(item["close_qfq"]) for item in prior_window), default=float("inf"))

    macd_bull = _has_bullish_cross(today["macd"], today["macd_signal"], prev["macd"], prev["macd_signal"])
    macd_bear = _has_bearish_cross(today["macd"], today["macd_signal"], prev["macd"], prev["macd_signal"])
    kdj_bull = _has_bullish_cross(today["kdj_k"], today["kdj_d"], prev["kdj_k"], prev["kdj_d"])
    kdj_bear = _has_bearish_cross(today["kdj_k"], today["kdj_d"], prev["kdj_k"], prev["kdj_d"])

    return {
        "buy_macd_kdj_double_cross": macd_bull and kdj_bull,
        "buy_ma_bullish_formation": today["ma5"] > today["ma10"] > today["ma20"] > today["ma60"]
        and not (prev["ma5"] > prev["ma10"] > prev["ma20"] > prev["ma60"]),
        "buy_volume_breakout_20d": bool(prior_window) and today["close_qfq"] > prior_high and today["volume_ratio"] > 1.5,
        "buy_rsi_rebound": _has_bullish_cross(today["rsi6"], today["rsi12"], prev["rsi6"], prev["rsi12"]) and prev["rsi6"] < 30,
        "sell_macd_kdj_double_cross": macd_bear and kdj_bear,
        "sell_ma_bearish_formation": today["ma5"] < today["ma10"] < today["ma20"] < today["ma60"]
        and not (prev["ma5"] < prev["ma10"] < prev["ma20"] < prev["ma60"]),
        "sell_volume_breakdown_20d": bool(prior_window) and today["close_qfq"] < prior_low and today["volume_ratio"] > 1.5,
        "sell_rsi_fall": _has_bearish_cross(today["rsi6"], today["rsi12"], prev["rsi6"], prev["rsi12"]) and prev["rsi6"] > 70,
    }


def _build_stock_entry(stock_row: dict[str, Any], *, signal_type: str, signal_side: str) -> dict[str, Any]:
    same_side_count = int(stock_row.get("signal_count_same_side", {}).get(signal_side, 0))
    return {
        "ts_code": stock_row.get("ts_code"),
        "name": stock_row.get("name"),
        "industry": stock_row.get("industry"),
        "close": stock_row.get("close"),
        "pct_chg": stock_row.get("pct_chg"),
        "volume_ratio": stock_row.get("volume_ratio"),
        "signal_count_same_side": same_side_count,
        "sort_score": {
            "strength_rank": same_side_count,
            "volume_rank_value": float(stock_row.get("volume_ratio") or 0.0),
            "pct_chg_rank_value": float(stock_row.get("pct_chg") or 0.0),
        },
        "metrics": dict(stock_row.get("metrics", {}).get(signal_type, {})),
    }


def build_signal_documents(*, trade_date: str, stock_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for signal_type in ALL_SIGNAL_TYPES:
        signal_side = "buy" if signal_type.startswith("buy_") else "sell"
        stocks = [
            _build_stock_entry(stock_row, signal_type=signal_type, signal_side=signal_side)
            for stock_row in stock_rows
            if stock_row.get("signal_hits", {}).get(signal_type)
        ]
        docs.append(
            {
                "trade_date": trade_date,
                "signal_type": signal_type,
                "signal_side": signal_side,
                "count": len(stocks),
                "stocks": stocks,
            }
        )
    return docs


def build_resonance_documents(*, trade_date: str, stock_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for signal_side in ("buy", "sell"):
        for resonance_level in RESONANCE_LEVELS:
            stocks: list[dict[str, Any]] = []
            for stock_row in stock_rows:
                signal_count = int(stock_row.get("signal_count_same_side", {}).get(signal_side, 0))
                if classify_resonance_level(signal_count) != resonance_level:
                    continue
                ordered_types = BUY_SIGNAL_TYPES if signal_side == "buy" else SELL_SIGNAL_TYPES
                signal_hits = stock_row.get("signal_hits", {})
                signal_types = [
                    signal_type
                    for signal_type in ordered_types
                    if signal_hits.get(signal_type)
                ]
                stocks.append(
                    {
                        "ts_code": stock_row.get("ts_code"),
                        "name": stock_row.get("name"),
                        "industry": stock_row.get("industry"),
                        "close": stock_row.get("close"),
                        "pct_chg": stock_row.get("pct_chg"),
                        "volume_ratio": stock_row.get("volume_ratio"),
                        "signal_count": signal_count,
                        "signal_types": signal_types,
                    }
                )
            docs.append(
                {
                    "trade_date": trade_date,
                    "signal_side": signal_side,
                    "resonance_level": resonance_level,
                    "min_signal_count": {"normal": 2, "strong": 3, "very_strong": 4}[resonance_level],
                    "count": len(stocks),
                    "stocks": stocks,
                }
            )
    return docs


def build_pattern_resonance_documents(*, trade_date: str, stock_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from app.signals.patterns.config import PATTERN_CATEGORIES, RESONANCE_THRESHOLDS
    docs: list[dict[str, Any]] = []
    for signal_side in ("buy", "sell"):
        for resonance_level in ("normal", "strong", "very_strong"):
            stocks: list[dict[str, Any]] = []
            for stock_row in stock_rows:
                weighted_score = int(stock_row.get("pattern_weighted_same_side", {}).get(signal_side, 0))
                if classify_resonance_level_weighted(weighted_score) != resonance_level:
                    continue
                unified_hits = stock_row.get("unified_hits", {})
                patterns = [p for p in unified_hits if unified_hits[p]]
                stocks.append(
                    {
                        "ts_code": stock_row.get("ts_code"),
                        "name": stock_row.get("name"),
                        "industry": stock_row.get("industry"),
                        "close": stock_row.get("close"),
                        "pct_chg": stock_row.get("pct_chg"),
                        "volume_ratio": stock_row.get("volume_ratio"),
                        "weighted_score": weighted_score,
                        "patterns": patterns,
                        "pattern_categories": {cat: [p for p in patterns if p in cfg["patterns"]] for cat, cfg in PATTERN_CATEGORIES.items()},
                    }
                )
            docs.append(
                {
                    "trade_date": trade_date,
                    "signal_side": signal_side,
                    "resonance_level": resonance_level,
                    "min_weighted_score": RESONANCE_THRESHOLDS[resonance_level],
                    "count": len(stocks),
                    "stocks": stocks,
                }
            )
    return docs


def _metrics_for_signal(signal_type: str, row: dict[str, Any], prev_row: dict[str, Any], prior_window: list[dict[str, Any]]) -> dict[str, Any]:
    if signal_type in {"buy_macd_kdj_double_cross", "sell_macd_kdj_double_cross"}:
        return {
            "macd": row.get("macd"),
            "macd_signal": row.get("macd_signal"),
            "kdj_k": row.get("kdj_k"),
            "kdj_d": row.get("kdj_d"),
        }
    if signal_type in {"buy_ma_bullish_formation", "sell_ma_bearish_formation"}:
        return {
            "ma5": row.get("ma5"),
            "ma10": row.get("ma10"),
            "ma20": row.get("ma20"),
            "ma60": row.get("ma60"),
        }
    if signal_type in {"buy_volume_breakout_20d", "sell_volume_breakdown_20d"}:
        prices = [float(item.get("close_qfq") or 0.0) for item in prior_window]
        return {
            "close_qfq": row.get("close_qfq"),
            "reference_price": max(prices) if signal_type.startswith("buy_") and prices else (min(prices) if prices else None),
            "volume_ratio": row.get("volume_ratio"),
        }
    return {
        "rsi6": row.get("rsi6"),
        "rsi12": row.get("rsi12"),
        "prev_rsi6": prev_row.get("rsi6"),
        "prev_rsi12": prev_row.get("rsi12"),
    }


def _sort_stock_rows(stock_rows: list[dict[str, Any]], *, signal_side: str) -> list[dict[str, Any]]:
    return sorted(
        stock_rows,
        key=lambda item: (
            -int(item.get("signal_count_same_side", {}).get(signal_side, 0)),
            -float(item.get("volume_ratio") or 0.0),
            -float(item.get("pct_chg") or 0.0),
            str(item.get("ts_code") or ""),
        ),
    )


def _load_joined_market_frame(*, start_date: str, end_date: str) -> pd.DataFrame:
    daily_glob = str(settings.data_dir / "raw" / "daily" / "ts_code=*" / "year=*" / "part-*.parquet")
    indicator_glob = str(settings.data_dir / "features" / "indicators" / "ts_code=*" / "year=*" / "part-*.parquet")
    query = """
        SELECT d.ts_code,
               d.trade_date,
               d.open,
               d.high,
               d.low,
               d.close,
               d.pct_chg,
               i.close_qfq,
               i.ma5,
               i.ma10,
               i.ma20,
               i.ma30,
               i.ma60,
               i.ma90,
               i.ma250,
               i.macd,
               i.macd_signal,
               i.kdj_k,
               i.kdj_d,
               i.rsi6,
               i.rsi12,
               i.volume_ratio,
               i.boll_upper,
               i.boll_lower
        FROM read_parquet(?, hive_partitioning=1, union_by_name=true) d
        INNER JOIN read_parquet(?, hive_partitioning=1, union_by_name=true) i
          ON d.ts_code = i.ts_code AND d.trade_date = i.trade_date
        WHERE d.trade_date >= ? AND d.trade_date <= ?
        ORDER BY d.ts_code, d.trade_date
    """
    with get_connection(read_only=True) as con:
        return con.execute(query, [daily_glob, indicator_glob, start_date, end_date]).fetchdf()


def _load_limit_frame(*, start_date: str, end_date: str) -> pd.DataFrame:
    limit_glob = str(settings.data_dir / "raw" / "daily_limit" / "ts_code=*" / "year=*" / "part-*.parquet")
    query = """
        SELECT ts_code, trade_date, up_limit, down_limit
        FROM read_parquet(?, hive_partitioning=1, union_by_name=true)
        WHERE trade_date >= ? AND trade_date <= ?
        ORDER BY ts_code, trade_date
    """
    with get_connection(read_only=True) as con:
        return con.execute(query, [limit_glob, start_date, end_date]).fetchdf()





def _build_stock_rows_by_date(frame: pd.DataFrame, limit_frame: pd.DataFrame, *, target_dates: list[str]) -> dict[str, list[dict[str, Any]]]:
    if frame.empty:
        return {trade_date: [] for trade_date in target_dates}

    target_date_set = set(target_dates)
    ts_codes = sorted(frame["ts_code"].astype(str).unique().tolist())
    basics = get_stock_basic_map(ts_codes)
    stock_rows_by_date: dict[str, list[dict[str, Any]]] = {trade_date: [] for trade_date in target_dates}

    limit_by_ts = {}
    if not limit_frame.empty:
        for ts_code, group in limit_frame.groupby("ts_code", sort=False):
            limit_by_ts[str(ts_code)] = group.to_dict(orient="records")

    for ts_code, group in frame.groupby("ts_code", sort=False):
        records = group.to_dict(orient="records")
        by_date = {str(item["trade_date"]): item for item in records}
        dates = sorted(by_date)
        limit_records = limit_by_ts.get(str(ts_code), [])
        for index in range(1, len(dates)):
            trade_date = dates[index]
            if trade_date not in target_date_set:
                continue
            row = by_date[trade_date]
            prev_row = by_date[dates[index - 1]]
            prior_window = [by_date[date] for date in dates[max(0, index - 20) : index]]
            flags = _compute_signal_flags_from_context(row, prev_row, prior_window)
            signal_hits = {signal_type: hit for signal_type, hit in flags.items() if hit}
            buy_count = sum(1 for signal_type, hit in signal_hits.items() if hit and signal_type.startswith("buy_"))
            sell_count = sum(1 for signal_type, hit in signal_hits.items() if hit and signal_type.startswith("sell_"))
            metrics = {
                signal_type: _metrics_for_signal(signal_type, row, prev_row, prior_window)
                for signal_type in signal_hits
            }

            pattern_flags = compute_pattern_flags_for_stock(records, limit_records, target_date=trade_date)
            pattern_hits = {k: v for k, v in pattern_flags.items() if v}
            
            unified_hits = dict(pattern_hits)
            for signal_type, hit in signal_hits.items():
                if hit:
                    unified_hits[signal_type] = True
            
            buy_unified = [p for p in unified_hits if p in BUY_PATTERNS]
            sell_unified = [p for p in unified_hits if p in SELL_PATTERNS]
            buy_weighted = calculate_weighted_score(buy_unified)
            sell_weighted = calculate_weighted_score(sell_unified)

            stock_rows_by_date[trade_date].append(
                {
                    "ts_code": str(ts_code),
                    "name": basics.get(str(ts_code), {}).get("name"),
                    "industry": basics.get(str(ts_code), {}).get("industry"),
                    "close": row.get("close"),
                    "pct_chg": row.get("pct_chg"),
                    "volume_ratio": row.get("volume_ratio"),
                    "signal_count_same_side": {"buy": buy_count, "sell": sell_count},
                    "signal_hits": signal_hits,
                    "metrics": metrics,
                    "pattern_hits": pattern_hits,
                    "unified_hits": unified_hits,
                    "pattern_count_same_side": {"buy": len(buy_unified), "sell": len(sell_unified)},
                    "pattern_weighted_same_side": {"buy": buy_weighted, "sell": sell_weighted},
                    "pattern_resonance": {
                        "buy": classify_resonance_level_weighted(buy_weighted),
                        "sell": classify_resonance_level_weighted(sell_weighted),
                    },
                }
            )
    return stock_rows_by_date


def generate_daily_stock_signal_docs_for_range(
    *,
    start_date: str,
    end_date: str,
    lookback_days: int = 60,
    target_dates: list[str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    start_dt = dt.datetime.strptime(start_date, "%Y%m%d") - dt.timedelta(days=max(lookback_days * 2, 120))
    buffered_start = start_dt.strftime("%Y%m%d")
    frame = _load_joined_market_frame(start_date=buffered_start, end_date=end_date)
    limit_frame = _load_limit_frame(start_date=buffered_start, end_date=end_date)
    if frame.empty:
        return [], [], []

    dates_to_emit = sorted(set(target_dates or [date for date in frame["trade_date"].astype(str).unique().tolist() if start_date <= date <= end_date]))
    stock_rows_by_date = _build_stock_rows_by_date(frame, limit_frame=limit_frame, target_dates=dates_to_emit)
    signal_docs: list[dict[str, Any]] = []
    resonance_docs: list[dict[str, Any]] = []
    pattern_resonance_docs: list[dict[str, Any]] = []
    for trade_date in dates_to_emit:
        stock_rows = stock_rows_by_date.get(trade_date, [])
        signal_docs.extend(build_signal_documents(trade_date=trade_date, stock_rows=_sort_stock_rows(stock_rows, signal_side="buy")))
        resonance_docs.extend(build_resonance_documents(trade_date=trade_date, stock_rows=stock_rows))
        pattern_resonance_docs.extend(build_pattern_resonance_documents(trade_date=trade_date, stock_rows=stock_rows))
    return signal_docs, resonance_docs, pattern_resonance_docs
