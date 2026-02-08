#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
import time
from pathlib import Path

import pandas as pd
from tqdm import tqdm

SCRIPT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(SCRIPT_ROOT))

from app.core.config import settings  # noqa: E402
from app.data.mongo_trade_calendar import upsert_trade_calendar  # noqa: E402
from app.data.tushare_client import fetch_trade_calendar  # noqa: E402

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync trade calendar from TuShare into MongoDB."
    )
    parser.add_argument("--exchange", type=str, default="SSE", help="Exchange code")
    parser.add_argument("--start-date", type=str, default="20000101", help="YYYYMMDD")
    parser.add_argument("--end-date", type=str, default="20501231", help="YYYYMMDD")
    parser.add_argument("--sleep", type=float, default=0.3, help="Sleep seconds between calls")
    return parser.parse_args()


def _build_year_ranges(start_date: str, end_date: str) -> list[tuple[str, str]]:
    start = dt.datetime.strptime(start_date, "%Y%m%d")
    end = dt.datetime.strptime(end_date, "%Y%m%d")
    ranges = []
    for year in range(start.year, end.year + 1):
        year_start = dt.datetime(year, 1, 1)
        year_end = dt.datetime(year, 12, 31)
        if year == start.year:
            year_start = start
        if year == end.year:
            year_end = end
        ranges.append((year_start.strftime("%Y%m%d"), year_end.strftime("%Y%m%d")))
    return ranges


def _to_records(df: pd.DataFrame) -> list[dict[str, object]]:
    if df is None or df.empty:
        return []
    normalized = df.where(pd.notna(df), None)
    return normalized.to_dict(orient="records")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    args = parse_args()
    if not settings.tushare_token:
        raise SystemExit("TUSHARE_TOKEN is required")

    ranges = _build_year_ranges(args.start_date, args.end_date)
    total = 0
    progress = tqdm(ranges, total=len(ranges), desc="sync_trade_calendar", unit="range", dynamic_ncols=True)
    for start_date, end_date in progress:
        try:
            df = fetch_trade_calendar(
                exchange=args.exchange,
                start_date=start_date,
                end_date=end_date,
            )
            records = _to_records(df)
            inserted = upsert_trade_calendar(records)
            total += inserted
            progress.set_postfix(range=f"{start_date}-{end_date}", upserted=inserted, total=total)
        except Exception as exc:
            logger.exception("sync trade calendar failed for %s~%s: %s", start_date, end_date, exc)
        time.sleep(args.sleep)

    logger.info("sync_trade_calendar done, upserted=%s", total)


if __name__ == "__main__":
    main()
