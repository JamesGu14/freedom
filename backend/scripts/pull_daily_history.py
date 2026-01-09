#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import time
from pathlib import Path
import sys

import pandas as pd
import tushare as ts

SCRIPT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(SCRIPT_ROOT))

from app.core.config import settings
from app.data.duckdb_store import upsert_adj_factor, upsert_daily


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pull daily and adj_factor history from TuShare and store in DuckDB."
    )
    parser.add_argument("--start-date", type=str, default="", help="YYYYMMDD, override start date")
    parser.add_argument("--end-date", type=str, default="", help="YYYYMMDD, override end date")
    parser.add_argument(
        "--last-days",
        type=int,
        default=0,
        help="Pull the most recent N days (optionally ending at --end-date)",
    )
    parser.add_argument("--sleep", type=float, default=0.3, help="Sleep seconds between calls")
    return parser.parse_args()


def normalize_date(value: str | None) -> str:
    if value:
        return value
    return dt.datetime.now().strftime("%Y%m%d")


def build_date_list(start_date: str, end_date: str) -> list[str]:
    start = dt.datetime.strptime(start_date, "%Y%m%d")
    end = dt.datetime.strptime(end_date, "%Y%m%d")
    return [d.strftime("%Y%m%d") for d in pd.date_range(start, end)]


def pull_daily_by_date(pro: ts.pro_api, trade_date: str) -> pd.DataFrame:
    return pro.daily(trade_date=trade_date)


def pull_adj_by_date(pro: ts.pro_api, trade_date: str) -> pd.DataFrame:
    return pro.adj_factor(trade_date=trade_date)


def main() -> None:
    args = parse_args()

    end_date = normalize_date(args.end_date)
    if args.last_days and args.last_days > 0:
        end_dt = dt.datetime.strptime(end_date, "%Y%m%d")
        start_dt = end_dt - dt.timedelta(days=args.last_days - 1)
        start_date = start_dt.strftime("%Y%m%d")
    else:
        start_date = normalize_date(args.start_date) if args.start_date else end_date
    date_list = build_date_list(start_date, end_date)

    pro = ts.pro_api("e14d179a9b5acda0028ea672ecb535d9541402ba5e15e31687a4439e")
    for idx, trade_date in enumerate(date_list, start=1):
        try:
            api_start = time.perf_counter()
            daily_df = pull_daily_by_date(pro, trade_date)
            if daily_df.empty:
                print(f"[{idx}/{len(date_list)}] {trade_date} no trading data")
                continue
            adj_df = pull_adj_by_date(pro, trade_date)
            api_elapsed = time.perf_counter() - api_start

            write_start = time.perf_counter()
            inserted_daily = upsert_daily(daily_df)
            inserted_adj = upsert_adj_factor(adj_df)
            write_elapsed = time.perf_counter() - write_start
            print(
                f"[{idx}/{len(date_list)}] {trade_date} "
                f"daily={inserted_daily} adj_factor={inserted_adj} "
                f"api={api_elapsed:.3f}s write={write_elapsed:.3f}s"
            )
        except Exception as exc:
            print(f"[{idx}/{len(date_list)}] {trade_date} failed: {exc}")
        time.sleep(args.sleep)


if __name__ == "__main__":
    main()
