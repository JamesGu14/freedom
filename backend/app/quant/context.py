from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from app.data.duckdb_backtest_store import (
    get_market_factor_for_date,
    load_daily_basic_for_date,
    load_daily_for_date,
    load_daily_limit_for_date,
    load_indicators_for_date,
    list_stock_universe,
)
from app.data.mongo import get_collection


@dataclass(slots=True)
class DailyDataBundle:
    trade_date: str
    next_trade_date: str
    universe_df: pd.DataFrame
    frame_t: pd.DataFrame
    frame_t1: pd.DataFrame
    limit_t1: pd.DataFrame
    market_factor_t: dict[str, Any] | None
    sector_rows_t: list[dict[str, Any]]
    shenwan_member_codes_t: dict[str, list[str]]
    citic_member_codes_t: dict[str, list[str]]


def _active_members_query(trade_date: str) -> dict[str, Any]:
    return {
        "in_date": {"$lte": trade_date},
        "$or": [
            {"out_date": {"$exists": False}},
            {"out_date": None},
            {"out_date": ""},
            {"out_date": {"$gt": trade_date}},
        ],
    }


def _normalize_sw_code(value: Any) -> str:
    text = str(value or "").strip().upper()
    if not text:
        return ""
    if "." not in text:
        return f"{text}.SI"
    root, _ = text.split(".", 1)
    return f"{root}.SI"


def _normalize_ci_code(value: Any) -> str:
    text = str(value or "").strip().upper()
    if not text:
        return ""
    if "." not in text:
        return f"{text}.CI"
    root, _ = text.split(".", 1)
    return f"{root}.CI"


def _get_sector_strength_rows(*, trade_date: str, level: int = 3) -> list[dict[str, Any]]:
    sw_rows = list(
        get_collection("shenwan_daily").find(
            {"trade_date": trade_date, "level": level},
            {"_id": 0, "ts_code": 1, "name": 1, "rank": 1, "rank_total": 1, "pct_change": 1},
        )
    )
    ci_rows = list(
        get_collection("citic_daily").find(
            {"trade_date": trade_date, "level": level},
            {"_id": 0, "ts_code": 1, "name": 1, "rank": 1, "rank_total": 1, "pct_change": 1},
        )
    )
    rows: list[dict[str, Any]] = []
    for item in sw_rows:
        row = dict(item)
        row["source"] = "sw"
        rows.append(row)
    for item in ci_rows:
        row = dict(item)
        row["source"] = "ci"
        rows.append(row)
    return rows


def _get_shenwan_member_codes_for_date(*, trade_date: str) -> dict[str, list[str]]:
    query = _active_members_query(trade_date)
    cursor = get_collection("shenwan_industry_member").find(
        query,
        {"_id": 0, "ts_code": 1, "l3_code": 1},
    )
    grouped: dict[str, set[str]] = {}
    for row in cursor:
        ts_code = str(row.get("ts_code") or "").strip().upper()
        l3_code = _normalize_sw_code(row.get("l3_code"))
        if not ts_code or not l3_code:
            continue
        grouped.setdefault(ts_code, set()).add(l3_code)
    return {code: sorted(values) for code, values in grouped.items()}


def _get_citic_member_codes_for_date(*, trade_date: str) -> dict[str, list[str]]:
    query = _active_members_query(trade_date)
    cursor = get_collection("citic_industry_member").find(
        query,
        {"_id": 0, "cons_code": 1, "index_code": 1},
    )
    grouped: dict[str, set[str]] = {}
    for row in cursor:
        ts_code = str(row.get("cons_code") or "").strip().upper()
        index_code = _normalize_ci_code(row.get("index_code"))
        if not ts_code or not index_code:
            continue
        grouped.setdefault(ts_code, set()).add(index_code)
    return {code: sorted(values) for code, values in grouped.items()}


def _merge_frames(
    *,
    universe_df: pd.DataFrame,
    daily_df: pd.DataFrame,
    basic_df: pd.DataFrame,
    indicators_df: pd.DataFrame,
) -> pd.DataFrame:
    if universe_df.empty:
        return pd.DataFrame()
    frame = universe_df.copy()
    if daily_df is not None and not daily_df.empty:
        frame = frame.merge(daily_df, on="ts_code", how="left")
    if basic_df is not None and not basic_df.empty:
        frame = frame.merge(
            basic_df.drop(columns=["trade_date"], errors="ignore"),
            on="ts_code",
            how="left",
            suffixes=("", "_basic"),
        )
    if indicators_df is not None and not indicators_df.empty:
        frame = frame.merge(
            indicators_df.drop(columns=["trade_date"], errors="ignore"),
            on="ts_code",
            how="left",
            suffixes=("", "_ind"),
        )
    frame["ts_code"] = frame["ts_code"].astype(str)
    return frame


def load_daily_data_bundle(
    *,
    trade_date: str,
    next_trade_date: str,
    universe_df: pd.DataFrame | None = None,
) -> DailyDataBundle:
    base_universe = universe_df if universe_df is not None else list_stock_universe()
    daily_t = load_daily_for_date(trade_date)
    daily_basic_t = load_daily_basic_for_date(trade_date)
    indicators_t = load_indicators_for_date(trade_date)

    daily_t1 = load_daily_for_date(next_trade_date)
    limit_t1 = load_daily_limit_for_date(next_trade_date)
    market_factor_t = get_market_factor_for_date(trade_date=trade_date, ts_code="000300.SH")
    sector_rows_t = _get_sector_strength_rows(trade_date=trade_date, level=3)
    shenwan_member_codes_t = _get_shenwan_member_codes_for_date(trade_date=trade_date)
    citic_member_codes_t = _get_citic_member_codes_for_date(trade_date=trade_date)

    frame_t = _merge_frames(
        universe_df=base_universe,
        daily_df=daily_t,
        basic_df=daily_basic_t,
        indicators_df=indicators_t,
    )
    frame_t1 = base_universe[["ts_code"]].copy()
    frame_t1 = frame_t1.merge(daily_t1, on="ts_code", how="left")

    return DailyDataBundle(
        trade_date=trade_date,
        next_trade_date=next_trade_date,
        universe_df=base_universe,
        frame_t=frame_t,
        frame_t1=frame_t1,
        limit_t1=limit_t1,
        market_factor_t=market_factor_t,
        sector_rows_t=sector_rows_t,
        shenwan_member_codes_t=shenwan_member_codes_t,
        citic_member_codes_t=citic_member_codes_t,
    )
