#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
import time
import uuid
from pathlib import Path

import pandas as pd
from tqdm import tqdm

SCRIPT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(SCRIPT_ROOT))

from app.core.config import settings  # noqa: E402
from app.data.mongo_stock import get_stock_collection  # noqa: E402
from app.data.tushare_client import fetch_cyq_chips  # noqa: E402

logger = logging.getLogger(__name__)

OUTPUT_COLUMNS = ["ts_code", "trade_date", "price", "percent"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync chip distribution data from TuShare cyq_chips.")
    parser.add_argument("--trade-date", type=str, default="", help="Single trade date: YYYYMMDD")
    parser.add_argument("--start-date", type=str, default="", help="Start date: YYYYMMDD")
    parser.add_argument("--end-date", type=str, default="", help="End date: YYYYMMDD")
    parser.add_argument("--last-days", type=int, default=0, help="Pull most recent N calendar days")
    parser.add_argument("--ts-codes", type=str, default="", help="Comma-separated ts_code list")
    parser.add_argument("--sleep", type=float, default=2.0, help="Sleep seconds between API calls")
    return parser.parse_args()


def normalize_date(value: str | None) -> str:
    if not value:
        return ""
    text = str(value).strip().replace("-", "")
    if len(text) != 8 or not text.isdigit():
        raise ValueError(f"invalid date: {value}")
    return text


def resolve_dates(args: argparse.Namespace) -> tuple[str, str]:
    """Resolve start_date and end_date from args."""
    if args.trade_date and (args.start_date or args.end_date or args.last_days):
        raise ValueError("--trade-date cannot be used with --start-date/--end-date/--last-days")

    today = dt.datetime.now().strftime("%Y%m%d")

    if args.trade_date:
        date = normalize_date(args.trade_date)
        return (date, date)

    end_date = normalize_date(args.end_date) or today

    if args.last_days and args.last_days > 0:
        end_dt = dt.datetime.strptime(end_date, "%Y%m%d")
        start_dt = end_dt - dt.timedelta(days=args.last_days - 1)
        start_date = start_dt.strftime("%Y%m%d")
    else:
        start_date = normalize_date(args.start_date) or end_date

    return (start_date, end_date)


def get_stock_list(ts_codes_arg: str) -> list[str]:
    """Get list of ts_codes to process."""
    if ts_codes_arg:
        return [code.strip() for code in ts_codes_arg.split(",") if code.strip()]

    collection = get_stock_collection()
    cursor = collection.find({}, {"_id": 0, "ts_code": 1})
    codes = [doc["ts_code"] for doc in cursor if doc.get("ts_code")]
    return sorted(codes)


def partition_exists(ts_code: str, year: str) -> bool:
    """Check if partition already exists."""
    features_base = settings.data_dir / "features" / "cyq_chips"
    partition_dir = features_base / f"ts_code={ts_code}" / f"year={year}"
    return partition_dir.exists() and any(partition_dir.glob("*.parquet"))


def transform_chips_df(df: pd.DataFrame, ts_code: str) -> pd.DataFrame:
    """Transform chip distribution data."""
    if df is None or df.empty:
        return pd.DataFrame()

    data = df.copy()
    if "ts_code" not in data.columns:
        data["ts_code"] = ts_code

    if "trade_date" in data.columns:
        data["trade_date"] = data["trade_date"].astype(str).str.replace("-", "", regex=False)

    available = [col for col in OUTPUT_COLUMNS if col in data.columns]
    if "ts_code" not in available or "trade_date" not in available:
        return pd.DataFrame()

    data = data[available]
    for col in OUTPUT_COLUMNS:
        if col not in data.columns:
            data[col] = None

    data = data[OUTPUT_COLUMNS].drop_duplicates(subset=["ts_code", "trade_date", "price"], keep="last")
    return data


def save_chips_data(df: pd.DataFrame) -> int:
    """Save chip distribution data to Parquet."""
    if df is None or df.empty:
        return 0

    features_base = settings.data_dir / "features" / "cyq_chips"
    features_base.mkdir(parents=True, exist_ok=True)

    data = df.copy()
    data["trade_date"] = data["trade_date"].astype(str).str.replace("-", "", regex=False)
    data["year"] = data["trade_date"].str[:4]

    saved = 0
    for (ts_code, year), group in data.groupby(["ts_code", "year"], sort=False):
        partition_dir = features_base / f"ts_code={ts_code}" / f"year={year}"
        partition_dir.mkdir(parents=True, exist_ok=True)
        part_path = partition_dir / f"part-{uuid.uuid4().hex}.parquet"
        new_rows = group.drop(columns=["year"])
        new_rows.to_parquet(part_path, index=False, engine="pyarrow")
        saved += len(new_rows)

    return saved


def sync_stock_chips(ts_code: str, start_date: str, end_date: str, sleep_sec: float) -> dict:
    """Sync chip distribution data for a single stock."""
    try:
        start_year = int(start_date[:4]) if start_date else 2010
        end_year = int(end_date[:4]) if end_date else dt.datetime.now().year

        # Split by year if range is large to avoid 2000-record limit
        if end_year - start_year > 2:
            all_data = []
            for year in range(start_year, end_year + 1):
                if partition_exists(ts_code, str(year)):
                    continue

                year_start = f"{year}0101"
                year_end = f"{year}1231"
                df = fetch_cyq_chips(ts_code, start_date=year_start, end_date=year_end)
                if df is not None and not df.empty:
                    all_data.append(df)
                time.sleep(sleep_sec)

            df = pd.concat(all_data, ignore_index=True) if all_data else pd.DataFrame()
        else:
            df = fetch_cyq_chips(ts_code, start_date=start_date, end_date=end_date)

        if df is None or df.empty:
            return {"status": "no_data", "rows": 0}

        if len(df) >= 2000:
            logger.warning(f"{ts_code}: returned {len(df)} rows, may be truncated")

        transformed = transform_chips_df(df, ts_code)
        if transformed.empty:
            return {"status": "transform_failed", "rows": 0}

        saved = save_chips_data(transformed)
        return {"status": "success", "rows": saved}

    except Exception as e:
        logger.error(f"Failed to sync {ts_code}: {e}")
        return {"status": "error", "rows": 0}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    args = parse_args()
    start_date, end_date = resolve_dates(args)
    stock_list = get_stock_list(args.ts_codes)

    logger.info(f"Processing {len(stock_list)} stocks from {start_date} to {end_date}")

    total_saved = 0
    success_count = 0
    error_count = 0

    with tqdm(stock_list, desc="Syncing chip distribution") as pbar:
        for ts_code in pbar:
            result = sync_stock_chips(ts_code, start_date, end_date, args.sleep)

            if result["status"] == "success":
                success_count += 1
                total_saved += result["rows"]
            elif result["status"] == "error":
                error_count += 1

            pbar.set_postfix(code=ts_code, rows=result["rows"], ok=success_count, err=error_count)
            time.sleep(args.sleep)

    logger.info(f"Completed: {success_count} success, {error_count} errors, {total_saved} rows saved")


if __name__ == "__main__":
    main()
