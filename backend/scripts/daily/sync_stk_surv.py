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
from app.data import mongo_stk_surv  # noqa: E402
from app.data.mongo_data_sync_date import mark_sync_done  # noqa: E402
from app.data.tushare_client import fetch_stk_surv  # noqa: E402

logger = logging.getLogger(__name__)

OUTPUT_COLUMNS = [
    "ts_code",
    "name",
    "surv_date",
    "fund_visitors",
    "rece_place",
    "rece_mode",
    "rece_org",
    "org_type",
    "comp_rece",
]

# stk_surv returns at most 100 records per call.
# Use 7-day sliding windows to paginate over larger date ranges.
_CHUNK_DAYS = 7


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync institutional survey records from TuShare into MongoDB."
    )
    parser.add_argument("--trade-date", type=str, default="", help="Single date: YYYYMMDD or YYYY-MM-DD")
    parser.add_argument("--start-date", type=str, default="", help="Start date: YYYYMMDD or YYYY-MM-DD")
    parser.add_argument("--end-date", type=str, default="", help="End date: YYYYMMDD or YYYY-MM-DD")
    parser.add_argument(
        "--last-days",
        type=int,
        default=0,
        help="Pull most recent N calendar days",
    )
    parser.add_argument("--sleep", type=float, default=1.5, help="Sleep seconds between API calls")
    return parser.parse_args()


def normalize_date(value: str | None) -> str:
    if not value:
        return ""
    text = str(value).strip().replace("-", "")
    if len(text) != 8 or not text.isdigit():
        raise ValueError(f"invalid date: {value}")
    return text


def resolve_dates(args: argparse.Namespace) -> tuple[str, str]:
    """Return (start_date, end_date) as YYYYMMDD strings."""
    if args.trade_date and (args.start_date or args.end_date or args.last_days):
        raise ValueError("--trade-date cannot be used with --start-date/--end-date/--last-days")

    today = dt.datetime.now().strftime("%Y%m%d")
    end_date = normalize_date(args.end_date) or today

    if args.trade_date:
        d = normalize_date(args.trade_date)
        return d, d

    if args.last_days and args.last_days > 0:
        end_dt = dt.datetime.strptime(end_date, "%Y%m%d")
        start_dt = end_dt - dt.timedelta(days=args.last_days - 1)
        start_date = start_dt.strftime("%Y%m%d")
    else:
        start_date = normalize_date(args.start_date) or end_date

    return start_date, end_date


def build_chunks(start_date: str, end_date: str, chunk_days: int) -> list[tuple[str, str]]:
    """Split [start_date, end_date] into chunks of at most chunk_days calendar days."""
    start_dt = dt.datetime.strptime(start_date, "%Y%m%d")
    end_dt = dt.datetime.strptime(end_date, "%Y%m%d")
    chunks: list[tuple[str, str]] = []
    current = start_dt
    while current <= end_dt:
        chunk_end = min(current + dt.timedelta(days=chunk_days - 1), end_dt)
        chunks.append((current.strftime("%Y%m%d"), chunk_end.strftime("%Y%m%d")))
        current = chunk_end + dt.timedelta(days=1)
    return chunks


def transform_df(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    data = df.copy()
    for col in OUTPUT_COLUMNS:
        if col not in data.columns:
            data[col] = None

    data = data[OUTPUT_COLUMNS].copy()
    if "surv_date" in data.columns:
        data["surv_date"] = data["surv_date"].astype(str).str.replace("-", "", regex=False)

    data = data.drop_duplicates(subset=["ts_code", "surv_date", "rece_org"], keep="last")
    return data


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    args = parse_args()
    if not settings.tushare_token:
        raise SystemExit("TUSHARE_TOKEN is required")

    start_date, end_date = resolve_dates(args)
    chunks = build_chunks(start_date, end_date, _CHUNK_DAYS)

    logger.info(
        "sync_stk_surv start: start=%s end=%s chunks=%s sleep=%.2f",
        start_date,
        end_date,
        len(chunks),
        args.sleep,
    )

    total_upserted = 0
    total_api_rows = 0

    progress = tqdm(chunks, total=len(chunks), desc="sync_stk_surv", unit="chunk", dynamic_ncols=True)
    for idx, (chunk_start, chunk_end) in enumerate(progress, start=1):
        try:
            raw_df = fetch_stk_surv(start_date=chunk_start, end_date=chunk_end)
            api_rows = 0 if raw_df is None else len(raw_df)
            total_api_rows += api_rows

            if api_rows >= 100:
                logger.warning(
                    "chunk %s-%s returned %s rows (at limit); data may be truncated",
                    chunk_start,
                    chunk_end,
                    api_rows,
                )

            if raw_df is None or raw_df.empty:
                progress.set_postfix(chunk=f"{chunk_start}-{chunk_end}", status="no_data")
            else:
                normalized = transform_df(raw_df)
                if normalized.empty:
                    progress.set_postfix(chunk=f"{chunk_start}-{chunk_end}", status="empty_after_transform")
                else:
                    records = normalized.where(pd.notna(normalized), None).to_dict(orient="records")
                    upserted = mongo_stk_surv.upsert_batch(records)
                    total_upserted += upserted
                    progress.set_postfix(
                        chunk=f"{chunk_start}-{chunk_end}",
                        api_rows=api_rows,
                        upserted=upserted,
                    )
        except Exception as exc:
            logger.exception("[%s/%s] %s-%s failed: %s", idx, len(chunks), chunk_start, chunk_end, exc)

        if args.sleep > 0 and idx < len(chunks):
            time.sleep(args.sleep)

    mark_sync_done(end_date, "sync_stk_surv")
    logger.info(
        "sync_stk_surv done: api_rows=%s upserted=%s",
        total_api_rows,
        total_upserted,
    )


if __name__ == "__main__":
    main()
