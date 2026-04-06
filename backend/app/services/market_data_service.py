from __future__ import annotations

import duckdb
import pandas as pd

from app.core.config import settings
from app.data import mongo_ccass_hold, mongo_hk_hold, mongo_moneyflow_hsgt, mongo_stk_surv
from app.data.duckdb_store import get_connection


def _query_parquet(
    feature_dir: str,
    ts_code: str,
    start_date: str,
    end_date: str,
) -> list[dict]:
    parquet_root = settings.data_dir / "features" / feature_dir / f"ts_code={ts_code}"
    if not parquet_root.exists():
        return []
    part_glob = str(parquet_root / "year=*/part-*.parquet")
    query = (
        "SELECT * FROM read_parquet(?, union_by_name = true) "
        "WHERE ts_code = ? AND trade_date BETWEEN ? AND ? "
        "ORDER BY trade_date DESC"
    )
    with get_connection(read_only=True) as con:
        try:
            rows = con.execute(query, [part_glob, ts_code, start_date, end_date]).fetchdf()
        except (duckdb.CatalogException, duckdb.IOException):
            return []
    if rows.empty:
        return []
    rows = rows.where(pd.notna(rows), None)
    return rows.to_dict(orient="records")


def get_cyq_perf(ts_code: str, start_date: str, end_date: str) -> list[dict]:
    return _query_parquet("cyq_perf", ts_code, start_date, end_date)


def get_cyq_chips(ts_code: str, start_date: str, end_date: str) -> list[dict]:
    return _query_parquet("cyq_chips", ts_code, start_date, end_date)


def get_moneyflow_dc(ts_code: str, start_date: str, end_date: str) -> list[dict]:
    return _query_parquet("moneyflow_dc", ts_code, start_date, end_date)


def get_index_factors(ts_code: str, start_date: str, end_date: str) -> list[dict]:
    return _query_parquet("idx_factor_pro", ts_code, start_date, end_date)


def get_ccass_hold(ts_code: str, start_date: str, end_date: str) -> list[dict]:
    return mongo_ccass_hold.query_by_ts_code(ts_code, start_date, end_date)


def get_hk_hold(
    ts_code: str, start_date: str, end_date: str, exchange: str = ""
) -> list[dict]:
    if exchange:
        return mongo_hk_hold.query_by_exchange(exchange, start_date, end_date)
    return mongo_hk_hold.query_by_ts_code(ts_code, start_date, end_date)


def get_stk_surv(ts_code: str, start_date: str, end_date: str) -> list[dict]:
    return mongo_stk_surv.query_by_ts_code(ts_code, start_date, end_date)


def get_moneyflow_hsgt(start_date: str, end_date: str) -> list[dict]:
    return mongo_moneyflow_hsgt.query_by_date_range(start_date, end_date)
