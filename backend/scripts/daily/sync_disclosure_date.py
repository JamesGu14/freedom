#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
from pathlib import Path

import pandas as pd
from tqdm import tqdm

SCRIPT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(SCRIPT_ROOT))

from app.core.config import settings  # noqa: E402
from app.data.duckdb_financials import ensure_financial_tables, upsert_disclosure_date  # noqa: E402
from app.data.mongo_data_sync_date import mark_sync_done  # noqa: E402
from app.data.tushare_client import fetch_disclosure_date  # noqa: E402

logger = logging.getLogger(__name__)
_PAGE_SIZE = 3000


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync TuShare disclosure_date data into DuckDB.")
    parser.add_argument("--year", type=int, default=0, help="Year to sync (e.g., 2024), syncs all 4 standard periods")
    parser.add_argument("--period", type=str, default="", help="Single reporting period: YYYYMMDD (e.g., 20241231)")
    parser.add_argument("--recent", type=int, default=0, help="Sync most recent N reporting periods")
    parser.add_argument("--sleep", type=float, default=0.5, help="Sleep seconds between API calls")
    return parser.parse_args()


def normalize_period(value: str | None) -> str:
    text = str(value or "").strip().replace("-", "")
    if not text:
        return ""
    if len(text) != 8 or not text.isdigit():
        raise ValueError(f"invalid period: {value}")
    return text


def get_recent_periods(n: int) -> list[str]:
    """Get the most recent N reporting periods based on current date."""
    today = dt.datetime.now()
    year = today.year
    month = today.month
    
    standard_periods = [
        ("0331", 3),
        ("0630", 6),
        ("0930", 9),
        ("1231", 12),
    ]
    
    # Build list of periods up to current date
    all_periods = []
    for y in range(year - 1, year + 1):  # Include previous year
        for sp, sp_month in standard_periods:
            if y < year or (y == year and sp_month <= month):
                all_periods.append(f"{y}{sp}")
    
    # Sort and get most recent N
    all_periods.sort()
    return all_periods[-n:] if len(all_periods) >= n else all_periods


def get_periods_to_sync(args: argparse.Namespace) -> list[str]:
    """Return list of periods to sync based on CLI args."""
    if args.period:
        return [normalize_period(args.period)]
    
    if args.year:
        year = args.year
        return [f"{year}0331", f"{year}0630", f"{year}0930", f"{year}1231"]
    
    if args.recent:
        return get_recent_periods(args.recent)
    
    # Default: recent 2 periods
    return get_recent_periods(2)


def fetch_disclosure_date_with_pagination(period: str) -> list[dict]:
    """Fetch disclosure_date with pagination handling."""
    all_records = []
    offset = 0
    
    while True:
        df = fetch_disclosure_date(end_date=period, limit=_PAGE_SIZE, offset=offset)
        
        if df is None or df.empty:
            break
        
        all_records.extend(df.to_dict("records"))
        
        if len(df) < _PAGE_SIZE:
            break
        
        offset += _PAGE_SIZE
    
    return all_records


def sync_single_period(period: str) -> int:
    """Sync data for a single reporting period. Returns total upserted count."""
    logger.info("Syncing disclosure_date for period %s", period)
    
    records = fetch_disclosure_date_with_pagination(period)
    
    if not records:
        logger.info("No disclosure_date data for period %s", period)
        return 0
    
    df = pd.DataFrame(records)
    
    # Normalize date columns
    for col in ("ann_date", "end_date", "pre_date", "actual_date", "modify_date"):
        if col in df.columns:
            df[col] = df[col].map(lambda x: str(x).replace("-", "") if x not in (None, "") else None)
    
    upserted = upsert_disclosure_date(df)
    
    logger.info("sync_disclosure_date period=%s: records=%s, upserted=%s", period, len(records), upserted)
    return upserted


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    args = parse_args()
    if not settings.tushare_token:
        raise SystemExit("TUSHARE_TOKEN is required")
    
    periods = get_periods_to_sync(args)
    
    logger.info("sync_disclosure_date: periods=%s", periods)
    
    ensure_financial_tables()
    
    progress = tqdm(periods, total=len(periods), desc="sync_disclosure_date", unit="period")
    
    try:
        for idx, period in enumerate(progress, start=1):
            upserted = sync_single_period(period)
            
            # Mark sync done for this period
            mark_sync_done(period, "sync_disclosure_date")
            logger.info("Marked sync done for period %s", period)
            
            if args.sleep > 0 and idx < len(periods):
                import time
                time.sleep(args.sleep)
        
        logger.info("sync_disclosure_date completed for periods: %s", periods)
        
    except Exception as exc:
        logger.error("sync_disclosure_date failed: %s", exc)
        raise


if __name__ == "__main__":
    main()
