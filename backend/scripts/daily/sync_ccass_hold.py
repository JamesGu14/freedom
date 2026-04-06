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
from app.data import mongo_ccass_hold  # noqa: E402
from app.data.mongo import get_collection  # noqa: E402
from app.data.mongo_data_sync_date import mark_sync_done  # noqa: E402
from app.data.tushare_client import fetch_ccass_hold  # noqa: E402

logger = logging.getLogger(__name__)

OUTPUT_COLUMNS = [
    "trade_date",
    "ts_code",
    "name",
    "shareholding",
    "hold_nums",
    "hold_ratio",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync CCASS shareholding data from TuShare into MongoDB."
    )
    parser.add_argument("--trade-date", type=str, default="", help="Single trade date: YYYYMMDD or YYYY-MM-DD")
    parser.add_argument("--start-date", type=str, default="", help="Start date: YYYYMMDD or YYYY-MM-DD")
    parser.add_argument("--end-date", type=str, default="", help="End date: YYYYMMDD or YYYY-MM-DD")
    parser.add_argument(
        "--last-days",
        type=int,
        default=0,
        help="Pull most recent N calendar days (auto skip non-trading days)",
    )
    parser.add_argument("--sleep", type=float, default=2.0, help="Sleep seconds between API calls")
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

    return build_date_list(start_date, end_date)


def load_open_dates(start_date: str, end_date: str, exchange: str = "SSE") -> set[str]:
    collection = get_collection("trade_calendar")
    cursor = collection.find(
        {
            "exchange": exchange,
            "cal_date": {"$gte": start_date, "$lte": end_date},
            "is_open": {"$in": ["1", 1]},
        },
        {"_id": 0, "cal_date": 1},
    )
    dates = {str(doc.get("cal_date")) for doc in cursor if doc.get("cal_date")}
    if not dates:
        logger.warning(
            "trade_calendar has no open dates in range [%s, %s], all days will be skipped",
            start_date,
            end_date,
        )
    return dates


def normalize_trade_date(value: object, default_date: str) -> str:
    text = str(value or "").strip().replace("-", "")
    if len(text) == 8 and text.isdigit():
        return text
    return default_date


def transform_df(df: pd.DataFrame, trade_date: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    data = df.copy()
    if "trade_date" not in data.columns:
        data["trade_date"] = trade_date

    if "ts_code" not in data.columns:
        return pd.DataFrame()

    data["trade_date"] = data["trade_date"].apply(lambda x: normalize_trade_date(x, trade_date))

    for col in OUTPUT_COLUMNS:
        if col not in data.columns:
            data[col] = None

    data = data[OUTPUT_COLUMNS].drop_duplicates(subset=["ts_code", "trade_date"], keep="last")
    return data


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    args = parse_args()
    if not settings.tushare_token:
        raise SystemExit("TUSHARE_TOKEN is required")

    date_list = resolve_dates(args)
    if not date_list:
        logger.info("no dates to sync")
        return

    start_date = min(date_list)
    end_date = max(date_list)
    open_dates = load_open_dates(start_date, end_date)

    logger.info(
        "sync_ccass_hold start: start=%s end=%s days=%s sleep=%.2f",
        start_date,
        end_date,
        len(date_list),
        args.sleep,
    )

    total_upserted = 0
    total_api_rows = 0
    synced_days = 0
    skipped_non_trading = 0

    progress = tqdm(date_list, total=len(date_list), desc="sync_ccass_hold", unit="day", dynamic_ncols=True)
    for idx, trade_date in enumerate(progress, start=1):
        if trade_date not in open_dates:
            skipped_non_trading += 1
            progress.set_postfix(date=trade_date, status="skip")
            continue

        try:
            raw_df = fetch_ccass_hold(trade_date=trade_date)
            api_rows = 0 if raw_df is None else len(raw_df)
            total_api_rows += api_rows
            if raw_df is None or raw_df.empty:
                progress.set_postfix(date=trade_date, status="no_data")
            else:
                normalized_df = transform_df(raw_df, trade_date)
                if normalized_df.empty:
                    progress.set_postfix(date=trade_date, status="empty_after_transform")
                else:
                    records = normalized_df.where(pd.notna(normalized_df), None).to_dict(orient="records")
                    upserted = mongo_ccass_hold.upsert_batch(records)
                    total_upserted += upserted
                    synced_days += 1
                    mark_sync_done(trade_date, "sync_ccass_hold")
                    progress.set_postfix(
                        date=trade_date,
                        api_rows=api_rows,
                        upserted=upserted,
                    )
        except Exception as exc:
            logger.exception("[%s/%s] %s failed: %s", idx, len(date_list), trade_date, exc)

        if args.sleep > 0 and idx < len(date_list):
            time.sleep(args.sleep)

    logger.info(
        "sync_ccass_hold done: synced_days=%s skipped_non_trading=%s api_rows=%s upserted=%s",
        synced_days,
        skipped_non_trading,
        total_api_rows,
        total_upserted,
    )


if __name__ == "__main__":
    main()
