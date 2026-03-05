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
from app.data.mongo import get_collection  # noqa: E402
from app.data.mongo_market_index import DEFAULT_MARKET_INDEX_CODES  # noqa: E402
from app.data.tushare_client import fetch_idx_factor_pro  # noqa: E402

logger = logging.getLogger(__name__)

OUTPUT_COLUMNS = [
    "ts_code",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "pre_close",
    "change",
    "pct_change",
    "vol",
    "amount",
    "macd_bfq",
    "macd_dea_bfq",
    "macd_dif_bfq",
    "kdj_k_bfq",
    "kdj_d_bfq",
    "kdj_j_bfq",
    "rsi_6_bfq",
    "rsi_12_bfq",
    "boll_upper_bfq",
    "boll_mid_bfq",
    "boll_lower_bfq",
    "ma5_bfq",
    "ma10_bfq",
    "ma20_bfq",
    "ma30_bfq",
    "ma60_bfq",
    "ma90_bfq",
    "ma250_bfq",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync index technical factor data from TuShare idx_factor_pro.")
    parser.add_argument("--trade-date", type=str, default="", help="Single trade date: YYYYMMDD")
    parser.add_argument("--start-date", type=str, default="", help="Start date: YYYYMMDD")
    parser.add_argument("--end-date", type=str, default="", help="End date: YYYYMMDD")
    parser.add_argument("--last-days", type=int, default=0, help="Pull most recent N calendar days")
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


def get_index_list() -> list[str]:
    """Collect index ts_codes from market_index_dailybasic, shenwan_industry, and citic_industry."""
    codes: set[str] = set(DEFAULT_MARKET_INDEX_CODES)

    # Market indices from market_index_dailybasic
    try:
        market_codes = get_collection("market_index_dailybasic").distinct("ts_code")
        codes.update(c for c in market_codes if c)
    except Exception as exc:
        logger.warning("Failed to load market_index_dailybasic ts_codes: %s", exc)

    # Shenwan industry indices (levels 1/2/3)
    try:
        sw_codes = get_collection("shenwan_industry").distinct("index_code")
        codes.update(c for c in sw_codes if c)
    except Exception as exc:
        logger.warning("Failed to load shenwan_industry index_codes: %s", exc)

    # CITIC industry indices
    try:
        citic_codes = get_collection("citic_industry").distinct("index_code")
        codes.update(c for c in citic_codes if c)
    except Exception as exc:
        logger.warning("Failed to load citic_industry index_codes: %s", exc)

    return sorted(codes)


def partition_exists(ts_code: str, year: str) -> bool:
    features_base = settings.data_dir / "features" / "idx_factor_pro"
    partition_dir = features_base / f"ts_code={ts_code}" / f"year={year}"
    return partition_dir.exists() and any(partition_dir.glob("*.parquet"))


def transform_df(df: pd.DataFrame, ts_code: str) -> pd.DataFrame:
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

    data = data[OUTPUT_COLUMNS].drop_duplicates(subset=["ts_code", "trade_date"], keep="last")
    return data


def save_data(df: pd.DataFrame) -> int:
    if df is None or df.empty:
        return 0

    features_base = settings.data_dir / "features" / "idx_factor_pro"
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


def sync_index(ts_code: str, start_date: str, end_date: str, sleep_sec: float) -> dict:
    try:
        start_year = int(start_date[:4]) if start_date else 2010
        end_year = int(end_date[:4]) if end_date else dt.datetime.now().year

        # Split by year if range is large to avoid record limits
        if end_year - start_year > 2:
            all_data = []
            for year in range(start_year, end_year + 1):
                if partition_exists(ts_code, str(year)):
                    continue

                year_start = f"{year}0101"
                year_end = f"{year}1231"
                df = fetch_idx_factor_pro(ts_code=ts_code, start_date=year_start, end_date=year_end)
                if df is not None and not df.empty:
                    all_data.append(df)
                time.sleep(sleep_sec)

            df = pd.concat(all_data, ignore_index=True) if all_data else pd.DataFrame()
        else:
            df = fetch_idx_factor_pro(ts_code=ts_code, start_date=start_date, end_date=end_date)

        if df is None or df.empty:
            return {"status": "no_data", "rows": 0}

        transformed = transform_df(df, ts_code)
        if transformed.empty:
            return {"status": "transform_failed", "rows": 0}

        saved = save_data(transformed)
        return {"status": "success", "rows": saved}

    except Exception as e:
        logger.error("Failed to sync %s: %s", ts_code, e)
        return {"status": "error", "rows": 0}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    args = parse_args()
    start_date, end_date = resolve_dates(args)
    index_list = get_index_list()

    logger.info("Processing %d indices from %s to %s", len(index_list), start_date, end_date)

    total_saved = 0
    success_count = 0
    error_count = 0

    with tqdm(index_list, desc="Syncing idx_factor_pro") as pbar:
        for ts_code in pbar:
            result = sync_index(ts_code, start_date, end_date, args.sleep)

            if result["status"] == "success":
                success_count += 1
                total_saved += result["rows"]
            elif result["status"] == "error":
                error_count += 1

            pbar.set_postfix(code=ts_code, rows=result["rows"], ok=success_count, err=error_count)
            time.sleep(args.sleep)

    logger.info("Completed: %d success, %d errors, %d rows saved", success_count, error_count, total_saved)


if __name__ == "__main__":
    main()
