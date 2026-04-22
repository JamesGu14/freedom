#!/usr/bin/env python3
"""One-time migration: export all DuckDB native tables to partitioned Parquet files."""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(SCRIPT_ROOT))

import duckdb
from app.core.config import settings

TABLE_CONFIG = {
    "adj_factor": {"date_field": "trade_date"},
    "margin_detail": {"date_field": "trade_date"},
    "stk_holdernumber": {"date_field": "ann_date"},
    "balancesheet": {"date_field": "ann_date"},
    "income": {"date_field": "ann_date"},
    "cashflow": {"date_field": "ann_date"},
    "fina_indicator": {"date_field": "ann_date"},
    "fina_mainbz": {"date_field": "end_date"},
    "forecast": {"date_field": "ann_date"},
    "express": {"date_field": "ann_date"},
    "fina_audit": {"date_field": "ann_date"},
    "disclosure_date": {"date_field": "ann_date"},
}


def export_table(con: duckdb.DuckDBPyConnection, table_name: str, date_field: str) -> None:
    count = con.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0]
    if count == 0:
        print(f"  {table_name}: empty, skipping")
        return

    df = con.execute(f'SELECT * FROM "{table_name}"').fetchdf()
    df[date_field] = df[date_field].astype(str)
    df["year"] = df[date_field].str[:4]

    base_dir = settings.data_dir / "raw" / table_name
    base_dir.mkdir(parents=True, exist_ok=True)

    exported = 0
    for (ts_code, year), group in df.groupby(["ts_code", "year"], sort=False):
        partition_dir = base_dir / f"ts_code={ts_code}" / f"year={year}"
        partition_dir.mkdir(parents=True, exist_ok=True)
        part_path = partition_dir / "part-0000.parquet"
        data = group.drop(columns=["year"])
        data.to_parquet(part_path, index=False, engine="pyarrow")
        exported += len(data)

    print(f"  {table_name}: exported {exported:,} rows → {base_dir}")


def main() -> None:
    db_path = str(settings.duckdb_path)
    print(f"Reading from: {db_path}")
    con = duckdb.connect(db_path, read_only=True)

    for table_name, config in TABLE_CONFIG.items():
        export_table(con, table_name, config["date_field"])

    con.close()
    print("\nDone! All DuckDB tables exported to Parquet.")


if __name__ == "__main__":
    main()
