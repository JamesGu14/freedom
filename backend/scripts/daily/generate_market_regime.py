#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
from dataclasses import asdict
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(SCRIPT_ROOT))

from app.data.mongo import get_collection  # noqa: E402
from app.data.mongo_market_regime import upsert_market_regime  # noqa: E402
from app.signals.market_regime import compute_market_regime  # noqa: E402

from pymongo import MongoClient  # noqa: E402

from app.core.config import settings  # noqa: E402

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate daily market regime")
    parser.add_argument("--trade-date", type=str, default=None)
    parser.add_argument("--start-date", type=str, default=None)
    parser.add_argument("--end-date", type=str, default=None)
    parser.add_argument("--last-days", type=int, default=0)
    return parser.parse_args()


def normalize_date(value: str | None) -> str:
    if not value:
        return ""
    text = str(value).strip().replace("-", "")
    if len(text) != 8 or not text.isdigit():
        raise ValueError(f"invalid date: {value}")
    return text


def get_open_trading_days(start_date: str, end_date: str) -> list[str]:
    cursor = get_collection("trade_calendar").find(
        {"exchange": "SSE", "cal_date": {"$gte": start_date, "$lte": end_date}, "is_open": {"$in": ["1", 1]}},
        {"_id": 0, "cal_date": 1},
    ).sort("cal_date", 1)
    return [str(doc["cal_date"]) for doc in cursor if doc.get("cal_date")]


def resolve_dates(args: argparse.Namespace) -> list[str]:
    if args.trade_date and (args.start_date or args.end_date or args.last_days):
        raise ValueError("--trade-date cannot be used with --start-date/--end-date/--last-days")

    today = dt.datetime.now().strftime("%Y%m%d")
    if args.trade_date:
        return get_open_trading_days(normalize_date(args.trade_date), normalize_date(args.trade_date))

    end_date = normalize_date(args.end_date) or today
    if args.last_days and args.last_days > 0:
        end_dt = dt.datetime.strptime(end_date, "%Y%m%d")
        start_dt = end_dt - dt.timedelta(days=args.last_days - 1)
        start_date = start_dt.strftime("%Y%m%d")
    else:
        start_date = normalize_date(args.start_date) or end_date
    return get_open_trading_days(start_date, end_date)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    args = parse_args()
    dates = resolve_dates(args)
    if not dates:
        logger.info("no trading dates to process")
        return

    client = MongoClient(settings.mongodb_url)
    data_dir = str(settings.data_dir)
    docs = []
    for trade_date in dates:
        result = compute_market_regime(trade_date, client, settings.mongodb_db, data_dir)
        if result:
            docs.append(asdict(result))
            logger.info("%s → %s (score: %s)", trade_date, result.regime_label_cn, result.total_score)

    count = upsert_market_regime(docs)
    logger.info("generate_market_regime done: dates=%s docs=%s", len(dates), count)


if __name__ == "__main__":
    main()
