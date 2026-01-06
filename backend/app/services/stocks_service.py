from __future__ import annotations

from app.data.duckdb_store import (
    get_stock_basic_by_code,
    list_adj_factor,
    list_daily,
    list_industries,
    list_stock_basic,
    replace_stock_basic,
)
from app.data.tushare_client import fetch_stock_basic


def sync_stock_basic() -> dict[str, int]:
    df = fetch_stock_basic()
    count = replace_stock_basic(df)
    return {"rows": count}


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


def get_daily(ts_code: str) -> list[dict[str, object]]:
    return list_daily(ts_code)


def get_adj_factor(ts_code: str) -> list[dict[str, object]]:
    return list_adj_factor(ts_code)


def get_stock_basic_by_ts_code(ts_code: str) -> dict[str, object] | None:
    return get_stock_basic_by_code(ts_code)
