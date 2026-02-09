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

from app.data.mongo import get_collection  # noqa: E402
from app.data.mongo_strategy_job_run import finish_strategy_job_run, start_strategy_job_run  # noqa: E402
from app.services.strategy_signal_service import generate_strategy_signals_for_date  # noqa: E402

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate strategy signals for signal_date=T.")
    parser.add_argument("--signal-date", type=str, default="", help="Single signal date, format YYYYMMDD or YYYY-MM-DD")
    parser.add_argument("--start-date", type=str, default="", help="Range start date, format YYYYMMDD or YYYY-MM-DD")
    parser.add_argument("--end-date", type=str, default="", help="Range end date, format YYYYMMDD or YYYY-MM-DD")
    parser.add_argument(
        "--recompute-from-date",
        type=str,
        default="",
        help="Recompute from date to today, format YYYYMMDD or YYYY-MM-DD",
    )
    parser.add_argument("--strategy-id", type=str, default="", help="Optional filter by strategy_id")
    parser.add_argument("--strategy-version-id", type=str, default="", help="Optional filter by strategy_version_id")
    parser.add_argument("--sleep", type=float, default=0.0, help="Sleep seconds between dates")
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
    has_signal = bool(args.signal_date)
    has_range = bool(args.start_date or args.end_date)
    has_recompute = bool(args.recompute_from_date)
    mode_count = sum([1 if has_signal else 0, 1 if has_range else 0, 1 if has_recompute else 0])
    if mode_count > 1:
        raise ValueError("--signal-date, --start-date/--end-date, --recompute-from-date are mutually exclusive")

    today = dt.datetime.now().strftime("%Y%m%d")
    if has_signal:
        return [normalize_date(args.signal_date)]

    if has_recompute:
        start_date = normalize_date(args.recompute_from_date)
        return build_date_list(start_date, today)

    end_date = normalize_date(args.end_date) or today
    start_date = normalize_date(args.start_date) or end_date
    return build_date_list(start_date, end_date)


def load_open_dates(start_date: str, end_date: str, exchange: str = "SSE") -> set[str]:
    cursor = get_collection("trade_calendar").find(
        {
            "exchange": exchange,
            "cal_date": {"$gte": start_date, "$lte": end_date},
            "is_open": {"$in": ["1", 1]},
        },
        {"_id": 0, "cal_date": 1},
    )
    return {str(item.get("cal_date")) for item in cursor if item.get("cal_date")}


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    args = parse_args()

    date_list = resolve_dates(args)
    if not date_list:
        logger.info("no dates to process")
        return
    start_date = date_list[0]
    end_date = date_list[-1]
    open_dates = load_open_dates(start_date=start_date, end_date=end_date)
    if not open_dates:
        logger.warning("no open trade dates in [%s, %s], skip all", start_date, end_date)
        return

    strategy_id = str(args.strategy_id or "").strip() or None
    strategy_version_id = str(args.strategy_version_id or "").strip() or None
    logger.info(
        "generate_strategy_signals start: start=%s end=%s total_days=%s strategy_id=%s strategy_version_id=%s",
        start_date,
        end_date,
        len(date_list),
        strategy_id or "-",
        strategy_version_id or "-",
    )

    success = 0
    skipped = 0
    failed = 0
    upserted_total = 0
    with tqdm(total=len(date_list), desc="generate_strategy_signals", unit="day") as pbar:
        for signal_date in date_list:
            pbar.update(1)
            if signal_date not in open_dates:
                skipped += 1
                pbar.set_postfix_str(f"{signal_date} skip(non-trading)")
                continue
            start_strategy_job_run(
                job_name="generate_strategy_signals",
                run_date=signal_date,
                params={
                    "strategy_id": strategy_id or "",
                    "strategy_version_id": strategy_version_id or "",
                },
            )
            try:
                result = generate_strategy_signals_for_date(
                    signal_date=signal_date,
                    strategy_id=strategy_id,
                    strategy_version_id=strategy_version_id,
                )
                status = str(result.get("status") or "failed")
                upserted = int(result.get("total_upserted") or 0)
                upserted_total += upserted
                if status in {"success", "degraded"}:
                    success += 1
                else:
                    skipped += 1
                finish_strategy_job_run(
                    job_name="generate_strategy_signals",
                    run_date=signal_date,
                    status=status,
                    stats={
                        "total_upserted": upserted,
                        "version_count": len(result.get("version_stats") or []),
                    },
                    error_message=str(result.get("reason") or ""),
                )
                pbar.set_postfix_str(f"{signal_date} upserted={upserted} status={status}")
            except Exception as exc:
                failed += 1
                finish_strategy_job_run(
                    job_name="generate_strategy_signals",
                    run_date=signal_date,
                    status="failed",
                    stats={},
                    error_message=str(exc),
                )
                logger.exception("generate_strategy_signals failed: signal_date=%s", signal_date)
                pbar.set_postfix_str(f"{signal_date} failed")
            if args.sleep > 0:
                time.sleep(args.sleep)

    logger.info(
        "generate_strategy_signals done: success=%s skipped=%s failed=%s upserted=%s",
        success,
        skipped,
        failed,
        upserted_total,
    )


if __name__ == "__main__":
    main()

