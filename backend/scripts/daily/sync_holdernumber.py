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
from app.data.duckdb_shareholders import ensure_shareholder_tables, upsert_stk_holdernumber  # noqa: E402
from app.data.mongo_data_sync_date import mark_sync_done  # noqa: E402
from app.data.tushare_client import fetch_stk_holdernumber  # noqa: E402

logger = logging.getLogger(__name__)
_PAGE_SIZE = 5000


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync TuShare stk_holdernumber data into DuckDB.")
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
    date_list = resolve_dates(args)
    if not date_list:
        return []
    windows: list[tuple[str, str]] = []
    for start_idx in range(0, len(date_list), window_days):
        window = date_list[start_idx : start_idx + window_days]
        windows.append((window[0], window[-1]))
    return windows


def normalize_frame(frame):  # noqa: ANN001
    normalized = frame.copy()
    for column in ("ann_date", "end_date"):
        if column not in normalized.columns:
            continue
        values = normalized[column]
        normalized[column] = values.where(values.notna(), None)
        normalized[column] = normalized[column].map(
            lambda value: str(value).replace("-", "") if value not in (None, "") else None
        )
    return normalized


def fetch_holdernumber_page(start_date: str, end_date: str, offset: int):
    return fetch_stk_holdernumber(start_date=start_date, end_date=end_date, limit=_PAGE_SIZE, offset=offset)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    args = parse_args()
    if not settings.tushare_token:
        raise SystemExit("TUSHARE_TOKEN is required")

    ensure_shareholder_tables()
    windows = resolve_windows(args)
    total_rows = 0
    total_upserted = 0
    progress = tqdm(windows, total=len(windows), desc="sync_stk_holdernumber", unit="window", dynamic_ncols=True)
    for idx, (start_date, end_date) in enumerate(progress, start=1):
        window_rows = 0
        window_upserted = 0
        offset = 0
        while True:
            df = fetch_holdernumber_page(start_date, end_date, offset)
            if df is None or df.empty:
                break
            normalized = normalize_frame(df)
            window_rows += len(normalized)
            window_upserted += upsert_stk_holdernumber(normalized)
            if len(normalized) < _PAGE_SIZE:
                break
            offset += _PAGE_SIZE
        total_rows += window_rows
        total_upserted += window_upserted
        mark_sync_done(end_date, "sync_stk_holdernumber")
        progress.set_postfix(start_date=start_date, end_date=end_date, api_rows=window_rows, upserted=window_upserted)
        if args.sleep > 0 and idx < len(windows):
            time.sleep(args.sleep)

    logger.info(
        "sync_stk_holdernumber done: windows=%s api_rows=%s upserted=%s",
        len(windows),
        total_rows,
        total_upserted,
    )


if __name__ == "__main__":
    main()
