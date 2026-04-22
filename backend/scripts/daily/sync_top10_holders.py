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
from app.data.duckdb_store import get_connection  # noqa: E402
from app.data.mongo_data_sync_date import mark_sync_done  # noqa: E402
from app.data.mongo_top10_holders import upsert_batch  # noqa: E402
from app.data.tushare_client import fetch_top10_floatholders, fetch_top10_holders  # noqa: E402

logger = logging.getLogger(__name__)
_PAGE_SIZE = 5000


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync TuShare top10 holder datasets into MongoDB.")
    parser.add_argument("--dataset", required=True, choices=["top10_holders", "top10_floatholders"])
    parser.add_argument("--start-date", type=str, default="", help="Announcement start date: YYYYMMDD or YYYY-MM-DD")
    parser.add_argument("--end-date", type=str, default="", help="Announcement end date: YYYYMMDD or YYYY-MM-DD")
    parser.add_argument("--last-days", type=int, default=0, help="Pull most recent N calendar days by ann_date")
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
    ann_dates = load_ann_dates_from_holdernumber(start_date, end_date)
    if ann_dates:
        return ann_dates
    return [(start + dt.timedelta(days=offset)).strftime("%Y%m%d") for offset in range((end - start).days + 1)]


def load_ann_dates_from_holdernumber(start_date: str, end_date: str) -> list[str]:
    stk_root = settings.data_dir / "raw" / "stk_holdernumber"
    if not stk_root.exists():
        return []
    stk_glob = str(stk_root / "ts_code=*" / "year=*" / "part-*.parquet")
    try:
        with get_connection(read_only=True) as con:
            rows = con.execute(
                """
                SELECT DISTINCT ann_date
                FROM read_parquet(?, union_by_name=true)
                WHERE ann_date IS NOT NULL
                  AND ann_date >= ?
                  AND ann_date <= ?
                ORDER BY ann_date
                """,
                [stk_glob, start_date, end_date],
            ).fetchall()
    except Exception:  # noqa: BLE001
        return []
    return [row[0] for row in rows if row and row[0]]


def fetch_dataset_page(dataset: str, ann_date: str, offset: int):
    if dataset == "top10_holders":
        return fetch_top10_holders(ann_date=ann_date, limit=_PAGE_SIZE, offset=offset)
    if dataset == "top10_floatholders":
        return fetch_top10_floatholders(ann_date=ann_date, limit=_PAGE_SIZE, offset=offset)
    raise ValueError(f"unsupported dataset: {dataset}")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    args = parse_args()
    if not settings.tushare_token:
        raise SystemExit("TUSHARE_TOKEN is required")

    date_list = resolve_dates(args)
    total_rows = 0
    total_upserted = 0
    progress = tqdm(date_list, total=len(date_list), desc=f"sync_{args.dataset}", unit="day", dynamic_ncols=True)
    for idx, ann_date in enumerate(progress, start=1):
        date_rows = 0
        date_upserted = 0
        offset = 0
        while True:
            df = fetch_dataset_page(args.dataset, ann_date, offset)
            if df is None or df.empty:
                break
            records = df.where(df.notna(), None).to_dict(orient="records")
            date_rows += len(records)
            date_upserted += upsert_batch(args.dataset, records)
            if len(records) < _PAGE_SIZE:
                break
            offset += _PAGE_SIZE
        total_rows += date_rows
        total_upserted += date_upserted
        mark_sync_done(ann_date, f"sync_{args.dataset}")
        progress.set_postfix(ann_date=ann_date, api_rows=date_rows, upserted=date_upserted)
        if args.sleep > 0 and idx < len(date_list):
            time.sleep(args.sleep)

    logger.info(
        "sync_top10_holders done: dataset=%s days=%s api_rows=%s upserted=%s",
        args.dataset,
        len(date_list),
        total_rows,
        total_upserted,
    )


if __name__ == "__main__":
    main()
