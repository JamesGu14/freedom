#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
import time
from pathlib import Path

import pandas as pd
import tushare as ts
from tqdm import tqdm

SCRIPT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(SCRIPT_ROOT))

from app.core.config import settings
from app.data.duckdb_store import upsert_adj_factor
from app.data.mongo_trade_calendar import is_trading_day

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync adj_factor by trade date into DuckDB only."
    )
    parser.add_argument("--start-date", type=str, default="", help="YYYYMMDD or YYYY-MM-DD")
    parser.add_argument("--end-date", type=str, default="", help="YYYYMMDD or YYYY-MM-DD")
    parser.add_argument(
        "--last-days",
        type=int,
        default=0,
        help="Pull the most recent N calendar days (auto skip non-trading days)",
    )
    parser.add_argument("--sleep", type=float, default=0.3, help="Sleep seconds between calls")
    return parser.parse_args()


def normalize_date(value: str | None) -> str:
    if not value:
        return ""
    text = str(value).strip().replace("-", "")
    if len(text) != 8 or not text.isdigit():
        raise ValueError(f"invalid date: {value}")
    return text


def build_date_list(start_date: str, end_date: str) -> list[str]:
    start = dt.datetime.strptime(start_date, "%Y%m%d")
    end = dt.datetime.strptime(end_date, "%Y%m%d")
    if start > end:
        raise ValueError("start-date cannot be later than end-date")
    return [d.strftime("%Y%m%d") for d in pd.date_range(start, end)]


def resolve_dates(args: argparse.Namespace) -> list[str]:
    today = dt.datetime.now().strftime("%Y%m%d")
    end_date = normalize_date(args.end_date) or today

    if args.last_days and args.last_days > 0:
        end_dt = dt.datetime.strptime(end_date, "%Y%m%d")
        start_dt = end_dt - dt.timedelta(days=args.last_days - 1)
        start_date = start_dt.strftime("%Y%m%d")
    else:
        start_date = normalize_date(args.start_date) or end_date

    return build_date_list(start_date, end_date)


def pull_adj_by_date(pro: ts.pro_api, trade_date: str) -> pd.DataFrame:
    return pro.adj_factor(trade_date=trade_date)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    args = parse_args()

    if not settings.tushare_token:
        raise SystemExit("TUSHARE_TOKEN is required")

    date_list = resolve_dates(args)
    pro = ts.pro_api(settings.tushare_token)

    skipped_non_trading = 0
    total_rows = 0
    success_dates: list[str] = []
    failed_dates: list[str] = []

    progress = tqdm(date_list, total=len(date_list), desc="sync_adj_factor", unit="day", dynamic_ncols=True)
    for idx, trade_date in enumerate(progress, start=1):
        if not is_trading_day(trade_date, exchange="SSE"):
            skipped_non_trading += 1
            progress.set_postfix(date=trade_date, status="skip")
            continue

        try:
            api_start = time.perf_counter()
            adj_df = pull_adj_by_date(pro, trade_date)
            api_elapsed = time.perf_counter() - api_start
            if adj_df.empty:
                logger.info("[%s/%s] %s no adj_factor rows", idx, len(date_list), trade_date)
                progress.set_postfix(date=trade_date, status="no_data", api=f"{api_elapsed:.1f}s")
                success_dates.append(trade_date)
                continue

            write_start = time.perf_counter()
            inserted = upsert_adj_factor(adj_df)
            write_elapsed = time.perf_counter() - write_start

            total_rows += inserted
            success_dates.append(trade_date)
            progress.set_postfix(date=trade_date, adj=inserted, api=f"{api_elapsed:.1f}s", write=f"{write_elapsed:.1f}s")
        except Exception as exc:
            failed_dates.append(trade_date)
            logger.exception("[%s/%s] %s sync adj_factor failed: %s", idx, len(date_list), trade_date, exc)
            progress.set_postfix(date=trade_date, status="failed")

        time.sleep(args.sleep)

    logger.info(
        "sync_adj_factor done: days=%s skipped_non_trading=%s success=%s failed=%s adj=%s",
        len(date_list),
        skipped_non_trading,
        len(success_dates),
        len(failed_dates),
        total_rows,
    )
    if failed_dates:
        logger.warning("sync_adj_factor failed dates=%s count=%s", ",".join(failed_dates), len(failed_dates))


if __name__ == "__main__":
    main()
