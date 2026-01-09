from __future__ import annotations

import duckdb
import pandas as pd
import uuid
from pathlib import Path

from app.core.config import settings


def get_connection() -> duckdb.DuckDBPyConnection:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(settings.duckdb_path))


def replace_stock_basic(df: pd.DataFrame) -> int:
    if df.empty:
        return 0

    with get_connection() as con:
        con.register("df", df)
        con.execute("CREATE OR REPLACE TABLE stock_basic AS SELECT * FROM df")
        return df.shape[0]


def list_stock_basic(
    *,
    page: int = 1,
    page_size: int = 10,
    name: str | None = None,
    ts_code: str | None = None,
    industry: str | None = None,
) -> tuple[list[dict[str, object]], int]:
    where_clauses: list[str] = []
    params: list[object] = []

    if name:
        where_clauses.append("name ILIKE ?")
        params.append(f"%{name}%")
    if ts_code:
        where_clauses.append("ts_code ILIKE ?")
        params.append(f"%{ts_code}%")
    if industry:
        where_clauses.append("industry = ?")
        params.append(industry)

    where_sql = f" WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    offset = max(page - 1, 0) * page_size

    query = (
        "SELECT ts_code, symbol, name, area, industry, market, list_date "
        "FROM stock_basic"
        f"{where_sql} "
        "ORDER BY ts_code "
        "LIMIT ? OFFSET ?"
    )
    count_query = f"SELECT COUNT(*) FROM stock_basic{where_sql}"
    with get_connection() as con:
        try:
            total = con.execute(count_query, params).fetchone()[0]
            rows = con.execute(query, params + [page_size, offset]).fetchdf()
        except duckdb.CatalogException:
            return [], 0
    return rows.to_dict(orient="records"), int(total)


def list_industries() -> list[str]:
    query = (
        "SELECT DISTINCT industry FROM stock_basic "
        "WHERE industry IS NOT NULL AND industry <> '' "
        "ORDER BY industry"
    )
    with get_connection() as con:
        try:
            rows = con.execute(query).fetchall()
        except (duckdb.CatalogException, duckdb.IOException):
            return []
    return [row[0] for row in rows]


def upsert_daily(df: pd.DataFrame) -> int:
    if df.empty:
        return 0

    if "ts_code" not in df.columns or "trade_date" not in df.columns:
        raise ValueError("daily data must include ts_code and trade_date")

    daily_base = settings.data_dir / "raw" / "daily"
    daily_base.mkdir(parents=True, exist_ok=True)

    data = df.copy()
    data["trade_date"] = data["trade_date"].astype(str)
    data["year"] = data["trade_date"].str[:4]

    inserted = 0
    for (ts_code, year), group in data.groupby(["ts_code", "year"], sort=False):
        partition_dir = daily_base / f"ts_code={ts_code}" / f"year={year}"
        partition_dir.mkdir(parents=True, exist_ok=True)
        part_glob = str(partition_dir / "part-*.parquet")

        incoming_dates = group["trade_date"].unique()
        existing_dates: set[str] = set()
        if any(partition_dir.glob("part-*.parquet")):
            with get_connection() as con:
                con.register(
                    "incoming_dates",
                    pd.DataFrame({"trade_date": incoming_dates}),
                )
                try:
                    rows = con.execute(
                        """
                        SELECT DISTINCT p.trade_date
                        FROM read_parquet(?) AS p
                        JOIN incoming_dates d ON p.trade_date = d.trade_date
                        """,
                        [part_glob],
                    ).fetchall()
                    existing_dates = {row[0] for row in rows}
                except Exception:
                    existing_dates = set()

        new_rows = group[~group["trade_date"].isin(existing_dates)].drop(columns=["year"])
        if new_rows.empty:
            continue

        part_path = partition_dir / f"part-{uuid.uuid4().hex}.parquet"
        with get_connection() as con:
            con.register("df", new_rows)
            con.execute("COPY (SELECT * FROM df) TO ? (FORMAT 'parquet')", [str(part_path)])
        inserted += new_rows.shape[0]

    return inserted


def upsert_adj_factor(df: pd.DataFrame) -> int:
    if df.empty:
        return 0

    with get_connection() as con:
        con.register("df", df)
        con.execute("CREATE TABLE IF NOT EXISTS adj_factor AS SELECT * FROM df WHERE 1=0")
        con.execute(
            """
            INSERT INTO adj_factor
            SELECT df.*
            FROM df
            LEFT JOIN adj_factor a
              ON a.ts_code = df.ts_code AND a.trade_date = df.trade_date
            WHERE a.ts_code IS NULL
            """
        )
        return df.shape[0]


def list_daily(ts_code: str) -> list[dict[str, object]]:
    daily_root = settings.data_dir / "raw" / "daily" / f"ts_code={ts_code}"
    if not daily_root.exists():
        return []

    part_glob = str(daily_root / "year=*/part-*.parquet")
    query = (
        "SELECT ts_code, trade_date, open, high, low, close, vol, amount "
        "FROM read_parquet(?) WHERE ts_code = ? ORDER BY trade_date"
    )
    with get_connection() as con:
        try:
            rows = con.execute(query, [part_glob, ts_code]).fetchdf()
        except duckdb.CatalogException:
            return []
    return rows.to_dict(orient="records")


def list_adj_factor(ts_code: str) -> list[dict[str, object]]:
    query = (
        "SELECT ts_code, trade_date, adj_factor "
        "FROM adj_factor WHERE ts_code = ? ORDER BY trade_date"
    )
    with get_connection() as con:
        try:
            rows = con.execute(query, [ts_code]).fetchdf()
        except duckdb.CatalogException:
            return []
    return rows.to_dict(orient="records")


def get_stock_basic_by_code(ts_code: str) -> dict[str, object] | None:
    query = (
        "SELECT ts_code, name, industry, market "
        "FROM stock_basic WHERE ts_code = ? LIMIT 1"
    )
    with get_connection() as con:
        try:
            row = con.execute(query, [ts_code]).fetchone()
        except duckdb.CatalogException:
            return None
    if not row:
        return None
    return {"ts_code": row[0], "name": row[1], "industry": row[2], "market": row[3]}
