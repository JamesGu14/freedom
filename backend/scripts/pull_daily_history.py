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
from app.data.duckdb_store import get_connection, replace_stock_basic, upsert_adj_factor, upsert_daily
from app.data.tushare_client import fetch_stock_basic


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pull daily and adj_factor history from TuShare and store in DuckDB."
    )
    parser.add_argument("--start-date", type=str, default="", help="YYYYMMDD, override start date")
    parser.add_argument("--end-date", type=str, default="", help="YYYYMMDD, override end date")
    parser.add_argument("--sleep", type=float, default=0.3, help="Sleep seconds between calls")
    return parser.parse_args()


def normalize_date(value: str | None) -> str:
    if value:
        return value
    return dt.datetime.now().strftime("%Y%m%d")


def ensure_stock_basic() -> None:
    with get_connection() as con:
        try:
            existing = con.execute("SELECT COUNT(*) FROM stock_basic").fetchone()[0]
        except Exception:
            existing = 0
    if existing:
        return

    df = fetch_stock_basic()
    replace_stock_basic(df)


def load_stock_list() -> list[tuple[str, str]]:
    with get_connection() as con:
        rows = con.execute("SELECT ts_code, list_date FROM stock_basic").fetchall()
    return [(row[0], row[1]) for row in rows]


def pull_history(
    pro: ts.pro_api, ts_code: str, start_date: str, end_date: str
) -> tuple[pd.DataFrame, pd.DataFrame]:
    daily_df = pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
    adj_df = pro.adj_factor(ts_code=ts_code, start_date=start_date, end_date=end_date)
    return daily_df, adj_df


def main() -> None:
    args = parse_args()

    end_date = normalize_date(args.end_date)
    override_start = args.start_date or ""

    ensure_stock_basic()
    stock_list = load_stock_list()
    if not stock_list:
        raise SystemExit("No stock_basic data available")

    pro = ts.pro_api("e14d179a9b5acda0028ea672ecb535d9541402ba5e15e31687a4439e")

    for idx, (ts_code, list_date) in enumerate(stock_list, start=1):
        start_date = override_start or list_date
        try:
            daily_df, adj_df = pull_history(pro, ts_code, start_date, end_date)
            inserted_daily = upsert_daily(daily_df)
            inserted_adj = upsert_adj_factor(adj_df)
            print(
                f"[{idx}/{len(stock_list)}] {ts_code} {start_date}-{end_date} "
                f"daily={inserted_daily} adj_factor={inserted_adj}"
            )
        except Exception as exc:
            print(f"[{idx}/{len(stock_list)}] {ts_code} failed: {exc}")
        time.sleep(args.sleep)


if __name__ == "__main__":
    main()
