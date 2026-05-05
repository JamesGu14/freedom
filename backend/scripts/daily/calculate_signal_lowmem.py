#!/usr/bin/env python3
"""Backfill daily_signal with memory-efficient batch processing."""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
import time
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPT_ROOT))

from app.data.mongo import get_collection  # noqa: E402
from app.data.mongo_stock import list_stock_codes  # noqa: E402
from app.data.mongo_trade_calendar import is_trading_day  # noqa: E402
from scripts.strategy.second import EarlyBreakoutSignalModel  # noqa: E402
from scripts.strategy.third import DailySignalModel  # noqa: E402

BATCH_SIZE = 300
logger = logging.getLogger(__name__)


def normalize_date(value: str) -> str:
    return str(value).strip().replace("-", "")


def process_date_batched(trade_date: str, stock_list: list[str], batch_size: int = BATCH_SIZE) -> int:
    """Process a single date in batches to control memory."""
    if not is_trading_day(trade_date, exchange="SSE"):
        logger.info("%s is not a trading day, skipping", trade_date)
        return 0

    strategies = [
        ("EarlyBreakoutSignalModel", EarlyBreakoutSignalModel),
        ("DailySignalModel", DailySignalModel),
    ]

    all_docs: list[dict] = []
    total_stocks = len(stock_list)

    for batch_start in range(0, total_stocks, batch_size):
        batch = stock_list[batch_start:batch_start + batch_size]
        # Create fresh models per batch (no cache)
        for ts_code in batch:
            for strategy_name, strategy_cls in strategies:
                try:
                    model = strategy_cls(ts_code)
                    if model.df is None or model.df.empty:
                        continue
                    signal = model.predict_date(trade_date)
                    if signal == "BUY":
                        all_docs.append({
                            "trading_date": trade_date,
                            "stock_code": ts_code,
                            "strategy": strategy_name,
                            "signal": signal,
                            "created_at": dt.datetime.now(dt.UTC),
                        })
                except Exception:
                    continue

        logger.info(
            "  batch %d/%d done, buy_signals=%d",
            batch_start // batch_size + 1,
            (total_stocks + batch_size - 1) // batch_size,
            len(all_docs),
        )

    collection = get_collection("daily_signal")
    collection.delete_many({"trading_date": trade_date})
    if all_docs:
        collection.insert_many(all_docs)

    logger.info("trade_date=%s buy_signals=%d", trade_date, len(all_docs))
    return len(all_docs)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    args = parser.parse_args()

    start = normalize_date(args.start_date)
    end = normalize_date(args.end_date)

    import pandas as pd
    trading_days = [
        d.strftime("%Y%m%d")
        for d in pd.date_range(start, end)
        if is_trading_day(d.strftime("%Y%m%d"), exchange="SSE")
    ]
    logger.info("Trading days: %s", trading_days)

    stock_list = list_stock_codes()
    logger.info("Stocks: %d, batch_size: %d", len(stock_list), args.batch_size)

    for trade_date in trading_days:
        t0 = time.time()
        count = process_date_batched(trade_date, stock_list, args.batch_size)
        elapsed = time.time() - t0
        logger.info("== %s done: %d buy signals in %.1fs", trade_date, count, elapsed)

    logger.info("All done!")


if __name__ == "__main__":
    main()
