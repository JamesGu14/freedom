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

from app.core.config import settings
from app.data.duckdb_store import get_connection, upsert_daily


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


def build_year_ranges(start_date: str | None, end_date: str | None) -> list[tuple[str, str]]:
    if end_date:
        end = dt.datetime.strptime(end_date, "%Y%m%d")
    else:
        end = dt.datetime.now()

    if start_date:
        start = dt.datetime.strptime(start_date, "%Y%m%d")
    else:
        start = dt.datetime(end.year - 30, 1, 1)

    start_year = start.year
    end_year = end.year
    ranges: list[tuple[str, str]] = []
    for year in range(start_year, end_year + 1):
        year_start = f"{year}0101"
        year_end = f"{year}1231"
        if year == start_year and start_date:
            year_start = start_date
        if year == end_year and end_date:
            year_end = end_date
        ranges.append((year_start, year_end))
    return ranges


def main() -> None:
    args = parse_args()

    token = "e14d179a9b5acda0028ea672ecb535d9541402ba5e15e31687a4439e"
    if not token:
        raise SystemExit("TUSHARE_TOKEN is required")

    stock_list = load_stock_list()
    if not stock_list:
        raise SystemExit("No stock_basic data available")

    year_ranges = build_year_ranges(args.start_date or None, args.end_date or None)
    pro = ts.pro_api(token)

    for idx, ts_code in enumerate(stock_list, start=1):
        try:
            total_inserted = 0
            for start_date, end_date in year_ranges:
                daily_df = pro.daily(
                    ts_code=ts_code,
                    start_date=start_date,
                    end_date=end_date,
                )
                if daily_df.empty:
                    continue
                total_inserted += upsert_daily(daily_df)
                time.sleep(args.sleep)
            if total_inserted == 0:
                print(f"[{idx}/{len(stock_list)}] {ts_code} no data")
            else:
                print(f"[{idx}/{len(stock_list)}] {ts_code} daily={total_inserted}")
        except Exception as exc:
            print(f"[{idx}/{len(stock_list)}] {ts_code} failed: {exc}")
        time.sleep(args.sleep)


if __name__ == "__main__":
    main()
