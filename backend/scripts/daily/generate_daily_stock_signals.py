#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(SCRIPT_ROOT))

from app.data.mongo import get_collection  # noqa: E402
from app.data.mongo_daily_stock_signals import (  # noqa: E402
    upsert_daily_stock_pattern_resonance,
    upsert_daily_stock_signal_resonance,
    upsert_daily_stock_signals,
)
from app.signals.daily_stock_signals import generate_daily_stock_signal_docs_for_range  # noqa: E402

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate daily stock signals")
    parser.add_argument("--trade-date", type=str, default=None, help="YYYYMMDD or YYYY-MM-DD")
    parser.add_argument("--start-date", type=str, default=None, help="YYYYMMDD or YYYY-MM-DD")
    parser.add_argument("--end-date", type=str, default=None, help="YYYYMMDD or YYYY-MM-DD")
    parser.add_argument("--last-days", type=int, default=0, help="Most recent N natural days")
    return parser.parse_args()


def normalize_date(value: str | None) -> str:
    if not value:
        return ""
    text = str(value).strip().replace("-", "")
    if len(text) != 8 or not text.isdigit():
        raise ValueError(f"invalid date: {value}")
    return text


def get_open_trading_days(start_date: str, end_date: str, exchange: str = "SSE") -> list[str]:
    cursor = get_collection("trade_calendar").find(
        {
            "exchange": exchange,
            "cal_date": {"$gte": start_date, "$lte": end_date},
            "is_open": {"$in": ["1", 1]},
        },
        {"_id": 0, "cal_date": 1},
    ).sort("cal_date", 1)
    return [str(doc.get("cal_date")) for doc in cursor if doc.get("cal_date")]


def resolve_dates(args: argparse.Namespace) -> list[str]:
    if args.trade_date and (args.start_date or args.end_date or args.last_days):
        raise ValueError("--trade-date cannot be used with --start-date/--end-date/--last-days")

    today = dt.datetime.now().strftime("%Y%m%d")
    if args.trade_date:
        trade_date = normalize_date(args.trade_date)
        return get_open_trading_days(trade_date, trade_date)

    end_date = normalize_date(args.end_date) or today
    if args.last_days and args.last_days > 0:
        end_dt = dt.datetime.strptime(end_date, "%Y%m%d")
        start_dt = end_dt - dt.timedelta(days=args.last_days - 1)
        start_date = start_dt.strftime("%Y%m%d")
    else:
        start_date = normalize_date(args.start_date) or end_date
    return get_open_trading_days(start_date, end_date)


def generate_for_date(trade_date: str) -> dict[str, object]:
    signal_docs, resonance_docs, pattern_resonance_docs = generate_daily_stock_signal_docs_for_range(
        start_date=trade_date,
        end_date=trade_date,
        lookback_days=60,
    )
    signal_count = upsert_daily_stock_signals(signal_docs)
    resonance_count = upsert_daily_stock_signal_resonance(resonance_docs)
    pattern_resonance_count = upsert_daily_stock_pattern_resonance(pattern_resonance_docs)
    return {
        "trade_date": trade_date,
        "signal_docs": signal_count,
        "resonance_docs": resonance_count,
        "pattern_resonance_docs": pattern_resonance_count,
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    args = parse_args()
    dates = resolve_dates(args)
    if not dates:
        logger.info("no trading dates to process")
        return

    signal_docs, resonance_docs, pattern_resonance_docs = generate_daily_stock_signal_docs_for_range(
        start_date=min(dates),
        end_date=max(dates),
        lookback_days=60,
        target_dates=dates,
    )
    signal_count = upsert_daily_stock_signals(signal_docs)
    resonance_count = upsert_daily_stock_signal_resonance(resonance_docs)
    pattern_resonance_count = upsert_daily_stock_pattern_resonance(pattern_resonance_docs)
    logger.info(
        "generate_daily_stock_signals done: dates=%s signal_docs=%s resonance_docs=%s pattern_resonance_docs=%s",
        len(dates),
        signal_count,
        resonance_count,
        pattern_resonance_count,
    )


if __name__ == "__main__":
    main()
