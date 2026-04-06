#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
import time
from pathlib import Path

from tqdm import tqdm

SCRIPT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(SCRIPT_ROOT))

from app.core.config import settings  # noqa: E402
from app.data.mongo_data_sync_date import mark_sync_done  # noqa: E402
from app.data.mongo_suspend_d import upsert_batch  # noqa: E402
from app.data.mongo_trade_calendar import is_trading_day  # noqa: E402
from app.data.tushare_client import fetch_suspend_d  # noqa: E402

logger = logging.getLogger(__name__)
_PAGE_SIZE = 5000


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync TuShare suspend_d data into MongoDB.")
    parser.add_argument("--trade-date", type=str, default="", help="Single trade date: YYYYMMDD or YYYY-MM-DD")
    parser.add_argument("--start-date", type=str, default="", help="Start date: YYYYMMDD or YYYY-MM-DD")
    parser.add_argument("--end-date", type=str, default="", help="End date: YYYYMMDD or YYYY-MM-DD")
    parser.add_argument("--last-days", type=int, default=0, help="Pull most recent N calendar days")
    parser.add_argument("--sleep", type=float, default=1.0, help="Sleep seconds between API calls")
    return parser.parse_args()


def normalize_date(value: str | None) -> str:
    text = str(value or "").strip().replace("-", "")
    if not text:
        return ""
    if len(text) != 8 or not text.isdigit():
        raise ValueError(f"invalid date: {value}")
    return text


def resolve_dates(args: argparse.Namespace) -> list[str]:
    if args.trade_date and (args.start_date or args.end_date or args.last_days):
        raise ValueError("--trade-date cannot be used with --start-date/--end-date/--last-days")

    today = dt.datetime.now().strftime("%Y%m%d")
    end_date = normalize_date(args.end_date) or today
    if args.trade_date:
        return [normalize_date(args.trade_date)]
    if args.last_days and args.last_days > 0:
        end_dt = dt.datetime.strptime(end_date, "%Y%m%d")
        start_dt = end_dt - dt.timedelta(days=args.last_days - 1)
        start_date = start_dt.strftime("%Y%m%d")
    else:
        start_date = normalize_date(args.start_date) or end_date
    start = dt.datetime.strptime(start_date, "%Y%m%d")
    end = dt.datetime.strptime(end_date, "%Y%m%d")
    return [(start + dt.timedelta(days=offset)).strftime("%Y%m%d") for offset in range((end - start).days + 1)]


def transform_records(records: list[dict[str, object]], trade_date: str) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    for record in records:
        item = dict(record)
        item["trade_date"] = normalize_date(str(item.get("trade_date") or trade_date)) or trade_date
        if item.get("suspend_date"):
            item["suspend_date"] = normalize_date(str(item.get("suspend_date"))) or item.get("suspend_date")
        if item.get("resume_date"):
            item["resume_date"] = normalize_date(str(item.get("resume_date"))) or item.get("resume_date")
        normalized.append(item)
    return normalized


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    args = parse_args()
    if not settings.tushare_token:
        raise SystemExit("TUSHARE_TOKEN is required")

    date_list = resolve_dates(args)
    total_upserted = 0
    total_api_rows = 0
    synced_dates: list[str] = []
    progress = tqdm(date_list, total=len(date_list), desc="sync_suspend_d", unit="day", dynamic_ncols=True)
    for idx, trade_date in enumerate(progress, start=1):
        if not is_trading_day(trade_date, exchange="SSE"):
            progress.set_postfix(date=trade_date, status="skip")
            continue
        date_rows = 0
        date_upserted = 0
        offset = 0
        while True:
            df = fetch_suspend_d(trade_date=trade_date, limit=_PAGE_SIZE, offset=offset)
            if df is None or df.empty:
                break
            records = transform_records(df.where(df.notna(), None).to_dict(orient="records"), trade_date)
            date_rows += len(records)
            date_upserted += upsert_batch(records)
            if len(records) < _PAGE_SIZE:
                break
            offset += _PAGE_SIZE
        total_api_rows += date_rows
        total_upserted += date_upserted
        mark_sync_done(trade_date, "sync_suspend_d")
        synced_dates.append(trade_date)
        progress.set_postfix(date=trade_date, api_rows=date_rows, upserted=date_upserted)
        if args.sleep > 0 and idx < len(date_list):
            time.sleep(args.sleep)

    logger.info(
        "sync_suspend_d done: days=%s synced=%s api_rows=%s upserted=%s",
        len(date_list),
        len(synced_dates),
        total_api_rows,
        total_upserted,
    )


if __name__ == "__main__":
    main()
