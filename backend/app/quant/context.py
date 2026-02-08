from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from app.data.duckdb_backtest_store import (
    get_market_factor_for_date,
    get_sector_strength_rows,
    load_daily_basic_for_date,
    load_daily_for_date,
    load_daily_limit_for_date,
    load_indicators_for_date,
    list_stock_universe,
)


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
    sector_rows_t = get_sector_strength_rows(trade_date=trade_date, level=3)

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
    )

