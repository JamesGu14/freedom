#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import logging
import time
from pathlib import Path
import sys

import tushare as ts

SCRIPT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(SCRIPT_ROOT))

from app.data.duckdb_store import (
    has_stock_data,
    upsert_daily,
    upsert_daily_basic,
    upsert_daily_limit,
)
from app.data.mongo_stock import list_stock_codes

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pull full daily history for each stock and store parquet."
    )
    parser.add_argument("--start-date", type=str, default="", help="YYYYMMDD, optional")
    parser.add_argument("--end-date", type=str, default="", help="YYYYMMDD, optional")
    parser.add_argument("--sleep", type=float, default=0.3, help="Sleep seconds between calls")
    return parser.parse_args()


def load_stock_list() -> list[str]:
    try:
        return list_stock_codes()
    except Exception as exc:
        raise SystemExit(f"failed to load stock_basic from MongoDB: {exc}") from exc


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
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
            logger.info("[%s/%s] %s skipped (data exists)", idx, len(stock_list), ts_code)
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
                logger.info(
                    "[%s/%s] %s no data elapsed=%.2fs",
                    idx,
                    len(stock_list),
                    ts_code,
                    stock_elapsed,
                )
            else:
                logger.info(
                    "[%s/%s] %s daily=%s elapsed=%.2fs",
                    idx,
                    len(stock_list),
                    ts_code,
                    total_inserted,
                    stock_elapsed,
                )
        except Exception as exc:
            stock_elapsed = time.perf_counter() - stock_start
            logger.exception(
                "[%s/%s] %s failed elapsed=%.2fs: %s",
                idx,
                len(stock_list),
                ts_code,
                stock_elapsed,
                exc,
            )
        time.sleep(args.sleep)


if __name__ == "__main__":
    main()
