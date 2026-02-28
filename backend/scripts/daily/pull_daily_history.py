#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import logging
import time
from pathlib import Path
import sys

import pandas as pd
import tushare as ts
from tqdm import tqdm

SCRIPT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(SCRIPT_ROOT))

from app.core.config import settings
from app.data.duckdb_store import upsert_adj_factor, upsert_daily, upsert_daily_basic, upsert_daily_limit
from app.data.mongo_data_sync_date import mark_sync_done
from app.data.mongo_trade_calendar import is_trading_day

logger = logging.getLogger(__name__)


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


def pull_daily_basic_by_date(pro: ts.pro_api, trade_date: str) -> pd.DataFrame:
    return pro.daily_basic(trade_date=trade_date)


def pull_stk_limit_by_date(pro: ts.pro_api, trade_date: str) -> pd.DataFrame:
    return pro.stk_limit(trade_date=trade_date)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    args = parse_args()
    if not settings.tushare_token:
        raise SystemExit("TUSHARE_TOKEN is required")

    # 验证日期范围
    if args.start_date and args.end_date:
        start_normalized = normalize_date(args.start_date)
        end_normalized = normalize_date(args.end_date)
        if start_normalized > end_normalized:
            raise SystemExit(
                f"Error: start_date ({args.start_date}) cannot be after end_date ({args.end_date}). "
                f"Please check your date arguments."
            )

    end_date = normalize_date(args.end_date)
    if args.last_days and args.last_days > 0:
        end_dt = dt.datetime.strptime(end_date, "%Y%m%d")
        start_dt = end_dt - dt.timedelta(days=args.last_days - 1)
        start_date = start_dt.strftime("%Y%m%d")
    else:
        start_date = normalize_date(args.start_date) if args.start_date else end_date
    date_list = build_date_list(start_date, end_date)

    module_file = getattr(sys.modules[upsert_daily.__module__], "__file__", "unknown")
    logger.info("using upsert_daily from %s", module_file)

    pro = ts.pro_api(settings.tushare_token)
    skipped_non_trading = 0
    total_daily = 0
    total_adj = 0
    total_basic = 0
    total_limit = 0
    adj_failed_dates: list[str] = []

    synced_dates: list[str] = []
    progress = tqdm(date_list, total=len(date_list), desc="pull_daily_history", unit="day", dynamic_ncols=True)
    for idx, trade_date in enumerate(progress, start=1):
        if not is_trading_day(trade_date, exchange="SSE"):
            skipped_non_trading += 1
            progress.set_postfix(date=trade_date, status="skip")
            continue
        try:
            api_start = time.perf_counter()
            daily_df = pull_daily_by_date(pro, trade_date)
            if daily_df.empty:
                progress.set_postfix(date=trade_date, status="no_data")
                continue
            adj_df = pull_adj_by_date(pro, trade_date)
            api_elapsed = time.perf_counter() - api_start

            write_daily_start = time.perf_counter()
            inserted_daily = upsert_daily(daily_df)
            write_daily_elapsed = time.perf_counter() - write_daily_start
            if inserted_daily != len(daily_df):
                logger.warning(
                    "[%s/%s] %s daily count mismatch df=%s inserted=%s",
                    idx,
                    len(date_list),
                    trade_date,
                    len(daily_df),
                    inserted_daily,
                )

            write_adj_start = time.perf_counter()
            inserted_adj = 0
            try:
                inserted_adj = upsert_adj_factor(adj_df)
            except Exception as adj_exc:
                # DuckDB lock contention should not block daily/basic/limit writes.
                adj_failed_dates.append(trade_date)
                logger.warning(
                    "[%s/%s] %s adj_factor upsert failed, continue other datasets: %s",
                    idx,
                    len(date_list),
                    trade_date,
                    adj_exc,
                )
            write_adj_elapsed = time.perf_counter() - write_adj_start

            # daily_basic
            api_basic_start = time.perf_counter()
            basic_df = pull_daily_basic_by_date(pro, trade_date)
            api_basic_elapsed = time.perf_counter() - api_basic_start
            write_basic_start = time.perf_counter()
            inserted_basic = upsert_daily_basic(basic_df)
            write_basic_elapsed = time.perf_counter() - write_basic_start

            # daily_limit (stk_limit)
            api_limit_start = time.perf_counter()
            limit_df = pull_stk_limit_by_date(pro, trade_date)
            api_limit_elapsed = time.perf_counter() - api_limit_start
            write_limit_start = time.perf_counter()
            inserted_limit = upsert_daily_limit(limit_df)
            write_limit_elapsed = time.perf_counter() - write_limit_start

            total_daily += inserted_daily
            total_adj += inserted_adj
            total_basic += inserted_basic
            total_limit += inserted_limit
            synced_dates.append(trade_date)

            total_api = api_elapsed + api_basic_elapsed + api_limit_elapsed
            total_write = write_daily_elapsed + write_adj_elapsed + write_basic_elapsed + write_limit_elapsed
            progress.set_postfix(
                date=trade_date,
                daily=inserted_daily,
                adj=inserted_adj,
                basic=inserted_basic,
                limit=inserted_limit,
                api=f"{total_api:.1f}s",
                write=f"{total_write:.1f}s",
            )
        except Exception as exc:
            logger.exception("[%s/%s] %s failed: %s", idx, len(date_list), trade_date, exc)
        time.sleep(args.sleep)

    for d in synced_dates:
        mark_sync_done(d, "pull_daily")
    logger.info(
        "pull_daily_history done: days=%s skipped_non_trading=%s daily=%s adj=%s basic=%s limit=%s",
        len(date_list),
        skipped_non_trading,
        total_daily,
        total_adj,
        total_basic,
        total_limit,
    )
    if adj_failed_dates:
        logger.warning(
            "pull_daily_history adj_factor failed dates=%s count=%s",
            ",".join(adj_failed_dates),
            len(adj_failed_dates),
        )


if __name__ == "__main__":
    main()
