#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import time
from pathlib import Path
import sys

import tushare as ts

SCRIPT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(SCRIPT_ROOT))

from app.data.duckdb_store import (
    get_connection,
    has_stock_data,
    upsert_daily,
    upsert_daily_basic,
    upsert_daily_limit,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pull full daily history for each stock in DuckDB and store parquet."
    )
    parser.add_argument("--start-date", type=str, default="", help="YYYYMMDD, optional")
    parser.add_argument("--end-date", type=str, default="", help="YYYYMMDD, optional")
    parser.add_argument("--sleep", type=float, default=0.3, help="Sleep seconds between calls")
    return parser.parse_args()


def load_stock_list() -> list[str]:
    with get_connection() as con:
        try:
            rows = con.execute("SELECT ts_code FROM stock_basic ORDER BY ts_code").fetchall()
        except Exception as exc:
            raise SystemExit(f"failed to load stock_basic: {exc}") from exc
    return [row[0] for row in rows]


def main() -> None:
    args = parse_args()

    token = "e14d179a9b5acda0028ea672ecb535d9541402ba5e15e31687a4439e"
    if not token:
        raise SystemExit("TUSHARE_TOKEN is required")

    stock_list = load_stock_list()
    if not stock_list:
        raise SystemExit("No stock_basic data available")

    # Calculate default date range if not provided
    if args.end_date:
        end_date = args.end_date
    else:
        end_date = dt.datetime.now().strftime("%Y%m%d")

    if args.start_date:
        start_date = args.start_date
    else:
        end_dt = dt.datetime.strptime(end_date, "%Y%m%d")
        start_dt = dt.datetime(end_dt.year - 30, 1, 1)
        start_date = start_dt.strftime("%Y%m%d")

    pro = ts.pro_api(token)

    for idx, ts_code in enumerate(stock_list, start=1):
        stock_start = time.perf_counter()

        # Check if stock data already exists using DuckDB
        if has_stock_data(ts_code):
            print(f"[{idx}/{len(stock_list)}] {ts_code} skipped (data exists)")
            continue

        try:
            # Call API once with full date range
            daily_df = pro.daily(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date,
            )
            daily_basic_df = pro.daily_basic(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date,
            )
            daily_limit_df = pro.stk_limit(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date,
            )

            total_inserted = 0
            if not daily_df.empty:
                total_inserted += upsert_daily(daily_df)
            if not daily_basic_df.empty:
                total_inserted += upsert_daily_basic(daily_basic_df)
            if not daily_limit_df.empty:
                total_inserted += upsert_daily_limit(daily_limit_df)

            stock_elapsed = time.perf_counter() - stock_start
            if total_inserted == 0:
                print(f"[{idx}/{len(stock_list)}] {ts_code} no data elapsed={stock_elapsed:.2f}s")
            else:
                print(f"[{idx}/{len(stock_list)}] {ts_code} daily={total_inserted} elapsed={stock_elapsed:.2f}s")
        except Exception as exc:
            stock_elapsed = time.perf_counter() - stock_start
            print(f"[{idx}/{len(stock_list)}] {ts_code} failed: {exc} elapsed={stock_elapsed:.2f}s")
        time.sleep(args.sleep)


if __name__ == "__main__":
    main()
