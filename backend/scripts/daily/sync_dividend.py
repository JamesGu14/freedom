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
from app.data.mongo_dividend_history import upsert_batch  # noqa: E402
from app.data.tushare_client import fetch_dividend  # noqa: E402

logger = logging.getLogger(__name__)
_PAGE_SIZE = 5000


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync TuShare dividend data into dividend_history.")
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
    ann_dates = load_ann_dates_from_financials(start_date, end_date)
    if ann_dates:
        return ann_dates
    return [(start + dt.timedelta(days=offset)).strftime("%Y%m%d") for offset in range((end - start).days + 1)]


def load_ann_dates_from_financials(start_date: str, end_date: str) -> list[str]:
    query = """
        SELECT ann_date FROM (
            SELECT DISTINCT ann_date FROM income WHERE ann_date IS NOT NULL AND ann_date >= ? AND ann_date <= ?
            UNION
            SELECT DISTINCT ann_date FROM balancesheet WHERE ann_date IS NOT NULL AND ann_date >= ? AND ann_date <= ?
            UNION
            SELECT DISTINCT ann_date FROM cashflow WHERE ann_date IS NOT NULL AND ann_date >= ? AND ann_date <= ?
            UNION
            SELECT DISTINCT ann_date FROM fina_indicator WHERE ann_date IS NOT NULL AND ann_date >= ? AND ann_date <= ?
        ) t
        ORDER BY ann_date
    """
    try:
        with get_connection(read_only=True) as con:
            rows = con.execute(
                query,
                [start_date, end_date, start_date, end_date, start_date, end_date, start_date, end_date],
            ).fetchall()
    except Exception:  # noqa: BLE001
        return []
    return [row[0] for row in rows if row and row[0]]


def fetch_dividend_page(ann_date: str, offset: int):
    return fetch_dividend(ann_date=ann_date, offset=offset, limit=_PAGE_SIZE)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    args = parse_args()
    if not settings.tushare_token:
        raise SystemExit("TUSHARE_TOKEN is required")

    date_list = resolve_dates(args)
    total_rows = 0
    total_upserted = 0
    progress = tqdm(date_list, total=len(date_list), desc="sync_dividend", unit="day", dynamic_ncols=True)
    for idx, ann_date in enumerate(progress, start=1):
        date_rows = 0
        date_upserted = 0
        offset = 0
        while True:
            df = fetch_dividend_page(ann_date, offset)
            if df is None or df.empty:
                break
            records = df.where(df.notna(), None).to_dict(orient="records")
            date_rows += len(records)
            date_upserted += upsert_batch(records)
            if len(records) < _PAGE_SIZE:
                break
            offset += _PAGE_SIZE
        total_rows += date_rows
        total_upserted += date_upserted
        mark_sync_done(ann_date, "sync_dividend")
        progress.set_postfix(ann_date=ann_date, api_rows=date_rows, upserted=date_upserted)
        if args.sleep > 0 and idx < len(date_list):
            time.sleep(args.sleep)

    logger.info("sync_dividend done: days=%s api_rows=%s upserted=%s", len(date_list), total_rows, total_upserted)


if __name__ == "__main__":
    main()
