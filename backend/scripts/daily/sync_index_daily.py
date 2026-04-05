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
from app.data.mongo_index_data import DEFAULT_INDEX_DAILY_WHITELIST, upsert_index_daily_batch  # noqa: E402
from app.data.tushare_client import fetch_index_daily  # noqa: E402

logger = logging.getLogger(__name__)
_PAGE_SIZE = 5000


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync TuShare index_daily data into MongoDB.")
    parser.add_argument("--start-date", type=str, default="", help="Start date: YYYYMMDD or YYYY-MM-DD")
    parser.add_argument("--end-date", type=str, default="", help="End date: YYYYMMDD or YYYY-MM-DD")
    parser.add_argument("--last-days", type=int, default=0, help="Pull most recent N calendar days")
    parser.add_argument("--index-codes", type=str, default="", help="Comma separated index codes. Empty uses default whitelist")
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
    today = dt.datetime.now().strftime("%Y%m%d")
    end_date = normalize_date(args.end_date) or today
    if args.last_days and args.last_days > 0:
        end_dt = dt.datetime.strptime(end_date, "%Y%m%d")
        start_dt = end_dt - dt.timedelta(days=args.last_days - 1)
        start_date = start_dt.strftime("%Y%m%d")
    else:
        start_date = normalize_date(args.start_date) or end_date
    start = dt.datetime.strptime(start_date, "%Y%m%d")
    end = dt.datetime.strptime(end_date, "%Y%m%d")
    if start > end:
        raise ValueError("start_date cannot be later than end_date")
    return [(start + dt.timedelta(days=offset)).strftime("%Y%m%d") for offset in range((end - start).days + 1)]


def resolve_windows(args: argparse.Namespace, *, window_days: int = 31) -> list[tuple[str, str]]:
    dates = resolve_dates(args)
    if not dates:
        return []
    windows: list[tuple[str, str]] = []
    for start_idx in range(0, len(dates), window_days):
        window = dates[start_idx : start_idx + window_days]
        windows.append((window[0], window[-1]))
    return windows


def parse_index_codes(value: str) -> list[str]:
    parts = [item.strip() for item in str(value or "").split(",")]
    codes = [item for item in parts if item]
    return codes or list(DEFAULT_INDEX_DAILY_WHITELIST)


def fetch_index_daily_page(ts_code: str, start_date: str, end_date: str, offset: int):
    return fetch_index_daily(ts_code=ts_code, start_date=start_date, end_date=end_date, offset=offset, limit=_PAGE_SIZE)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    args = parse_args()
    if not settings.tushare_token:
        raise SystemExit("TUSHARE_TOKEN is required")

    index_codes = parse_index_codes(args.index_codes)
    windows = resolve_windows(args)
    total_rows = 0
    total_upserted = 0
    progress = tqdm(index_codes, total=len(index_codes), desc="sync_index_daily", unit="index", dynamic_ncols=True)
    for code_idx, ts_code in enumerate(progress, start=1):
        code_rows = 0
        code_upserted = 0
        for start_date, end_date in windows:
            offset = 0
            while True:
                df = fetch_index_daily_page(ts_code, start_date, end_date, offset)
                if df is None or df.empty:
                    break
                records = df.where(df.notna(), None).to_dict(orient="records")
                code_rows += len(records)
                code_upserted += upsert_index_daily_batch(records)
                if len(records) < _PAGE_SIZE:
                    break
                offset += _PAGE_SIZE
            mark_sync_done(end_date, "sync_index_daily")
            if args.sleep > 0:
                time.sleep(args.sleep)
        total_rows += code_rows
        total_upserted += code_upserted
        progress.set_postfix(ts_code=ts_code, api_rows=code_rows, upserted=code_upserted)

    logger.info("sync_index_daily done: indices=%s api_rows=%s upserted=%s", len(index_codes), total_rows, total_upserted)


if __name__ == "__main__":
    main()
