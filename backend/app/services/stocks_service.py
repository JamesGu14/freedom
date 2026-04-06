from __future__ import annotations

import pandas as pd

from app.data.duckdb_store import (
    list_adj_factor,
    list_daily,
    list_daily_changes_for_date,
    get_next_trade_date,
    list_indicators,
    list_last_n_days_pct_chg,
    list_latest_daily_changes,
)
from app.data.mongo_stock import (
    count_stock_basic,
    get_stock_basic_by_code,
    list_industries,
    list_stock_basic,
    upsert_stock_basic,
)
from app.data.tushare_client import fetch_stock_basic


def _normalize_df(df: pd.DataFrame) -> list[dict[str, object]]:
    if df.empty:
        return []
    normalized = df.where(pd.notna(df), None)
    return normalized.to_dict(orient="records")


def sync_stock_basic(source: str | None = None) -> dict[str, int | str]:
    source_value = (source or "tushare").lower()
    if source_value in {"mongo", "mongodb"}:
        mongo_count = count_stock_basic()
        if mongo_count == 0:
            raise ValueError("MongoDB stock_basic is empty or missing")
        return {"rows": mongo_count, "source": "mongo"}
    if source_value == "duckdb":
        raise ValueError("DuckDB stock_basic is no longer supported")

    try:
        df = fetch_stock_basic()
        records = _normalize_df(df)
        mongo_count = upsert_stock_basic(records)
        return {"rows": mongo_count, "source": "tushare"}
    except ValueError:
        if source is not None:
            raise
        mongo_count = count_stock_basic()
        if mongo_count == 0:
            raise ValueError("MongoDB stock_basic is empty or missing")
        return {"rows": mongo_count, "source": "mongo"}


def get_stock_basic(
    *,
    page: int = 1,
    page_size: int = 10,
    name: str | None = None,
    ts_code: str | None = None,
    industry: str | None = None,
) -> tuple[list[dict[str, object]], int]:
    return list_stock_basic(
        page=page,
        page_size=page_size,
        name=name,
        ts_code=ts_code,
        industry=industry,
    )


def get_industries() -> list[str]:
    return list_industries()


def get_daily(ts_code: str, *, limit: int | None = None) -> list[dict[str, object]]:
    return list_daily(ts_code, limit=limit)


def get_adj_factor(ts_code: str, *, limit: int | None = None) -> list[dict[str, object]]:
    return list_adj_factor(ts_code, limit=limit)


def get_stock_basic_by_ts_code(ts_code: str) -> dict[str, object] | None:
    return get_stock_basic_by_code(ts_code)


def get_indicators(ts_code: str, *, limit: int | None = None) -> list[dict[str, object]]:
    return list_indicators(ts_code, limit=limit)


def get_latest_daily_changes(ts_codes: list[str]) -> dict[str, dict[str, object]]:
    return list_latest_daily_changes(ts_codes)


def get_daily_changes_for_date(ts_codes: list[str], trade_date: str) -> dict[str, dict[str, object]]:
    return list_daily_changes_for_date(ts_codes, trade_date)


def get_next_trade_date_for_codes(ts_codes: list[str], trade_date: str) -> str | None:
    return get_next_trade_date(ts_codes, trade_date)


def get_last_n_days_pct_chg(
    ts_codes: list[str], n: int = 3
) -> dict[str, dict[str, object]]:
    return list_last_n_days_pct_chg(ts_codes, n=n)
