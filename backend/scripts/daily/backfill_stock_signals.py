#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(SCRIPT_ROOT))

from app.data.mongo import get_collection
from app.data.mongo_daily_stock_signals import (
    upsert_daily_stock_pattern_resonance,
    upsert_daily_stock_signal_resonance,
    upsert_daily_stock_signals,
)
from app.signals.daily_stock_signals import generate_daily_stock_signal_docs_for_range

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill daily stock signals historically")
    parser.add_argument("--start-date", type=str, default="20200101", help="YYYYMMDD")
    parser.add_argument("--end-date", type=str, default=None, help="YYYYMMDD (default: today)")
    parser.add_argument("--batch-days", type=int, default=30, help="Process N days at a time")
    parser.add_argument("--dry-run", action="store_true", help="Don't write to database")
    return parser.parse_args()


def normalize_date(value: str | None) -> str:
    if not value:
        today = dt.datetime.now()
        return today.strftime("%Y%m%d")
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


def process_batch(dates: list[str], dry_run: bool = False) -> dict[str, int]:
    if not dates:
        return {"signal_docs": 0, "resonance_docs": 0, "pattern_resonance_docs": 0}
    
    logger.info(f"Processing batch: {dates[0]} to {dates[-1]} ({len(dates)} days)")
    
    signal_docs, resonance_docs, pattern_resonance_docs = generate_daily_stock_signal_docs_for_range(
        start_date=min(dates),
        end_date=max(dates),
        lookback_days=60,
        target_dates=dates,
    )
    
    if dry_run:
        logger.info(f"DRY RUN: Would write {len(signal_docs)} signal docs, {len(resonance_docs)} resonance docs, {len(pattern_resonance_docs)} pattern resonance docs")
        return {
            "signal_docs": len(signal_docs),
            "resonance_docs": len(resonance_docs),
            "pattern_resonance_docs": len(pattern_resonance_docs),
        }
    
    signal_count = upsert_daily_stock_signals(signal_docs)
    resonance_count = upsert_daily_stock_signal_resonance(resonance_docs)
    pattern_resonance_count = upsert_daily_stock_pattern_resonance(pattern_resonance_docs)
    
    logger.info(f"Batch complete: signal_docs={signal_count}, resonance_docs={resonance_count}, pattern_resonance_docs={pattern_resonance_count}")
    
    return {
        "signal_docs": signal_count,
        "resonance_docs": resonance_count,
        "pattern_resonance_docs": pattern_resonance_count,
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    args = parse_args()
    
    start_date = normalize_date(args.start_date)
    end_date = normalize_date(args.end_date)
    batch_size = max(args.batch_days, 1)
    
    logger.info(f"Backfilling from {start_date} to {end_date}, batch_size={batch_size}")
    
    all_dates = get_open_trading_days(start_date, end_date)
    if not all_dates:
        logger.info("No trading dates to process")
        return
    
    logger.info(f"Found {len(all_dates)} trading days")
    
    totals = {"signal_docs": 0, "resonance_docs": 0, "pattern_resonance_docs": 0}
    
    for i in range(0, len(all_dates), batch_size):
        batch = all_dates[i:i + batch_size]
        result = process_batch(batch, dry_run=args.dry_run)
        for key in totals:
            totals[key] += result[key]
    
    logger.info(
        "Backfill complete: total_dates=%s signal_docs=%s resonance_docs=%s pattern_resonance_docs=%s",
        len(all_dates),
        totals["signal_docs"],
        totals["resonance_docs"],
        totals["pattern_resonance_docs"],
    )


if __name__ == "__main__":
    main()
