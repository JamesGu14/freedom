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
from app.data.duckdb_financials import (  # noqa: E402
    ensure_financial_tables,
    upsert_balancesheet,
    upsert_cashflow,
    upsert_express,
    upsert_fina_indicator,
    upsert_forecast,
    upsert_income,
)
from app.data.mongo_data_sync_date import mark_sync_done  # noqa: E402
from app.data.tushare_client import (  # noqa: E402
    fetch_balancesheet,
    fetch_cashflow,
    fetch_express,
    fetch_fina_indicator,
    fetch_forecast,
    fetch_income,
)

logger = logging.getLogger(__name__)
_PAGE_SIZE = 5000


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync TuShare financial report datasets into DuckDB.")
    parser.add_argument("--dataset", required=True, choices=["income", "balancesheet", "cashflow", "fina_indicator", "forecast", "express"])
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
    return [(start + dt.timedelta(days=offset)).strftime("%Y%m%d") for offset in range((end - start).days + 1)]


def resolve_windows(args: argparse.Namespace, *, window_days: int = 31) -> list[tuple[str, str]]:
    date_list = resolve_dates(args)
    if not date_list:
        return []
    if args.dataset == "forecast":
        return [(date_value, date_value) for date_value in date_list]
    windows: list[tuple[str, str]] = []
    for start_idx in range(0, len(date_list), window_days):
        window = date_list[start_idx : start_idx + window_days]
        windows.append((window[0], window[-1]))
    return windows


def fetch_dataset_page(dataset: str, start_date: str, end_date: str, offset: int):
    if dataset == "income":
        return fetch_income(start_date=start_date, end_date=end_date, limit=_PAGE_SIZE, offset=offset)
    if dataset == "balancesheet":
        return fetch_balancesheet(start_date=start_date, end_date=end_date, limit=_PAGE_SIZE, offset=offset)
    if dataset == "cashflow":
        return fetch_cashflow(start_date=start_date, end_date=end_date, limit=_PAGE_SIZE, offset=offset)
    if dataset == "fina_indicator":
        return fetch_fina_indicator(start_date=start_date, end_date=end_date, limit=_PAGE_SIZE, offset=offset)
    if dataset == "forecast":
        return fetch_forecast(ann_date=end_date, limit=_PAGE_SIZE, offset=offset)
    if dataset == "express":
        return fetch_express(start_date=start_date, end_date=end_date, limit=_PAGE_SIZE, offset=offset)
    raise ValueError(f"unsupported dataset: {dataset}")


def normalize_date_columns(frame):  # noqa: ANN001
    normalized = frame.copy()
    for column in ("ann_date", "f_ann_date", "end_date"):
        if column not in normalized.columns:
            continue
        values = normalized[column]
        normalized[column] = values.where(values.notna(), None)
        normalized[column] = normalized[column].map(
            lambda value: str(value).replace("-", "") if value not in (None, "") else None
        )
    return normalized


def _upsert_dataset(dataset: str, records_df) -> int:  # noqa: ANN001
    if dataset == "income":
        return upsert_income(records_df)
    if dataset == "balancesheet":
        return upsert_balancesheet(records_df)
    if dataset == "cashflow":
        return upsert_cashflow(records_df)
    if dataset == "fina_indicator":
        return upsert_fina_indicator(records_df)
    if dataset == "forecast":
        return upsert_forecast(records_df)
    if dataset == "express":
        return upsert_express(records_df)
    raise ValueError(f"unsupported dataset: {dataset}")


def _task_name(dataset: str) -> str:
    return f"sync_{dataset}"


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    args = parse_args()
    if not settings.tushare_token:
        raise SystemExit("TUSHARE_TOKEN is required")

    ensure_financial_tables()
    windows = resolve_windows(args)
    total_rows = 0
    total_upserted = 0
    progress = tqdm(windows, total=len(windows), desc=f"sync_{args.dataset}", unit="window", dynamic_ncols=True)
    for idx, (start_date, end_date) in enumerate(progress, start=1):
        window_rows = 0
        window_upserted = 0
        offset = 0
        while True:
            df = fetch_dataset_page(args.dataset, start_date, end_date, offset)
            if df is None or df.empty:
                break
            normalized = normalize_date_columns(df)
            window_rows += len(normalized)
            window_upserted += _upsert_dataset(args.dataset, normalized)
            if len(normalized) < _PAGE_SIZE:
                break
            offset += _PAGE_SIZE
        total_rows += window_rows
        total_upserted += window_upserted
        mark_sync_done(end_date, _task_name(args.dataset))
        progress.set_postfix(start_date=start_date, end_date=end_date, api_rows=window_rows, upserted=window_upserted)
        if args.sleep > 0 and idx < len(windows):
            time.sleep(args.sleep)

    logger.info(
        "sync_financial_reports done: dataset=%s windows=%s api_rows=%s upserted=%s",
        args.dataset,
        len(windows),
        total_rows,
        total_upserted,
    )


if __name__ == "__main__":
    main()
