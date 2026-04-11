#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
from pathlib import Path

from tqdm import tqdm

SCRIPT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(SCRIPT_ROOT))

from app.core.config import settings  # noqa: E402
from app.data.duckdb_financials import ensure_financial_tables, upsert_fina_mainbz  # noqa: E402
from app.data.mongo_data_sync_date import mark_sync_done  # noqa: E402
from app.data.mongo_stock import list_stock_codes  # noqa: E402
from app.data.tushare_client import fetch_fina_mainbz  # noqa: E402

logger = logging.getLogger(__name__)
_PAGE_SIZE = 100


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync TuShare fina_mainbz data into DuckDB.")
    parser.add_argument("--period", type=str, default="", help="Single reporting period: YYYYMMDD (e.g., 20241231)")
    parser.add_argument("--period-start", type=str, default="", help="Reporting period range start: YYYYMMDD")
    parser.add_argument("--period-end", type=str, default="", help="Reporting period range end: YYYYMMDD")
    parser.add_argument("--ts-codes", type=str, default="", help="Comma-separated stock codes for testing")
    parser.add_argument("--sleep", type=float, default=1.5, help="Sleep seconds between API calls")
    return parser.parse_args()


def normalize_period(value: str | None) -> str:
    text = str(value or "").strip().replace("-", "")
    if not text:
        return ""
    if len(text) != 8 or not text.isdigit():
        raise ValueError(f"invalid period: {value}")
    return text


def get_ts_codes(args: argparse.Namespace) -> list[str]:
    if args.ts_codes:
        return [code.strip() for code in args.ts_codes.split(",") if code.strip()]
    return list_stock_codes()


def get_periods_to_sync(args: argparse.Namespace) -> list[str]:
    """Return list of periods to sync based on CLI args."""
    if args.period:
        return [normalize_period(args.period)]
    
    if args.period_start and args.period_end:
        start = normalize_period(args.period_start)
        end = normalize_period(args.period_end)
        # Generate standard reporting periods within the range
        periods = []
        start_year = int(start[:4])
        end_year = int(end[:4])
        standard_periods = ["0331", "0630", "0930", "1231"]
        for year in range(start_year, end_year + 1):
            for sp in standard_periods:
                period = f"{year}{sp}"
                if start <= period <= end:
                    periods.append(period)
        return sorted(periods)
    
    # Default: current period
    today = dt.datetime.now()
    year = today.year
    month = today.month
    if month <= 3:
        return [f"{year}0331"]
    elif month <= 6:
        return [f"{year}0630"]
    elif month <= 9:
        return [f"{year}0930"]
    else:
        return [f"{year}1231"]


def fetch_fina_mainbz_with_pagination(ts_code: str, period: str | None = None, period_start: str | None = None, period_end: str | None = None) -> list[dict]:
    """Fetch fina_mainbz with pagination handling."""
    all_records = []
    offset = 0
    
    while True:
        if period:
            df = fetch_fina_mainbz(ts_code=ts_code, period=period, limit=_PAGE_SIZE, offset=offset)
        else:
            df = fetch_fina_mainbz(ts_code=ts_code, start_date=period_start, end_date=period_end, limit=_PAGE_SIZE, offset=offset)
        
        if df is None or df.empty:
            break
        
        all_records.extend(df.to_dict("records"))
        
        if len(df) < _PAGE_SIZE:
            break
        
        offset += _PAGE_SIZE
    
    return all_records


def sync_single_period(period: str, ts_codes: list[str], sleep: float) -> int:
    """Sync data for a single reporting period. Returns total upserted count."""
    total_upserted = 0
    empty_count = 0
    
    progress = tqdm(ts_codes, total=len(ts_codes), desc=f"sync_fina_mainbz_{period}", unit="stock", dynamic_ncols=True)
    
    for idx, ts_code in enumerate(progress, start=1):
        try:
            records = fetch_fina_mainbz_with_pagination(ts_code, period=period)
            
            if not records:
                empty_count += 1
                logger.debug("No fina_mainbz data for %s in period %s", ts_code, period)
                continue
            
            import pandas as pd
            df = pd.DataFrame(records)
            
            # Normalize date columns
            for col in ("end_date",):
                if col in df.columns:
                    df[col] = df[col].map(lambda x: str(x).replace("-", "") if x not in (None, "") else None)
            
            upserted = upsert_fina_mainbz(df)
            total_upserted += upserted
            
            progress.set_postfix(ts_code=ts_code, upserted=upserted, total=total_upserted)
            
            if sleep > 0 and idx < len(ts_codes):
                import time
                time.sleep(sleep)
                
        except Exception as exc:
            logger.warning("Failed to fetch fina_mainbz for %s: %s", ts_code, exc)
            continue
    
    logger.info("sync_fina_mainbz period=%s: stocks=%s, empty=%s, upserted=%s", period, len(ts_codes), empty_count, total_upserted)
    return total_upserted


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    args = parse_args()
    if not settings.tushare_token:
        raise SystemExit("TUSHARE_TOKEN is required")
    
    periods = get_periods_to_sync(args)
    ts_codes = get_ts_codes(args)
    
    logger.info("sync_fina_mainbz: periods=%s, stocks=%s", periods, len(ts_codes))
    
    ensure_financial_tables()
    
    try:
        for period in periods:
            upserted = sync_single_period(period, ts_codes, args.sleep)
            
            # Mark sync done for this period only after all stocks are processed
            if upserted > 0 or True:  # Mark even if 0 to indicate we processed it
                mark_sync_done(period, "sync_fina_mainbz")
                logger.info("Marked sync done for period %s", period)
        
        logger.info("sync_fina_mainbz completed for periods: %s", periods)
        
    except Exception as exc:
        logger.error("sync_fina_mainbz failed: %s", exc)
        raise


if __name__ == "__main__":
    main()
