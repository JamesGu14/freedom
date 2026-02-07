#!/usr/bin/env python3
"""
Optimized signal calculation script with:
1. Parallel processing using ProcessPoolExecutor
2. Strategy instance caching per stock
3. Batch processing for dates
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from tqdm import tqdm

SCRIPT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(SCRIPT_ROOT))

from app.data.mongo import get_collection
from app.data.mongo_stock import list_stock_codes
from app.data.mongo_trade_calendar import is_trading_day
from scripts.strategy.second import EarlyBreakoutSignalModel
from scripts.strategy.third import DailySignalModel

logger = logging.getLogger(__name__)

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Calculate daily signals for a given trading date and store BUY signals (optimized)."
    )
    parser.add_argument("--given-date", type=str, required=False, help="YYYYMMDD or YYYY-MM-DD")
    parser.add_argument("--start-date", type=str, required=False, help="Start date: YYYYMMDD or YYYY-MM-DD")
    parser.add_argument("--end-date", type=str, required=False, help="End date: YYYYMMDD or YYYY-MM-DD (default: today)")
    parser.add_argument("--workers", type=int, default=4, help="Number of parallel workers (default: 4)")
    parser.add_argument("--batch-size", type=int, default=100, help="Stock batch size per worker (default: 100)")
    return parser.parse_args()


def normalize_date(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("date is required")
    if "-" in value:
        return dt.datetime.strptime(value, "%Y-%m-%d").strftime("%Y%m%d")
    if len(value) == 8:
        return value
    raise ValueError("date must be YYYYMMDD or YYYY-MM-DD")


def get_trading_days(start_date: str, end_date: str) -> list[str]:
    """Get all trading days in date range."""
    start = normalize_date(start_date)
    end = normalize_date(end_date)
    start_dt = dt.datetime.strptime(start, "%Y%m%d")
    end_dt = dt.datetime.strptime(end, "%Y%m%d")
    if start_dt > end_dt:
        raise ValueError("start_date cannot be after end_date")

    dates: list[str] = []
    current = start_dt
    while current <= end_dt:
        date_str = current.strftime("%Y%m%d")
        if is_trading_day(date_str, exchange="SSE"):
            dates.append(date_str)
        current += dt.timedelta(days=1)
    return dates


class StrategyCache:
    """Cache strategy instances per stock to avoid recreating them for each date."""
    
    def __init__(self):
        self._cache: dict[str, dict[str, object]] = {}
        self._strategies = [
            ("EarlyBreakoutSignalModel", EarlyBreakoutSignalModel),
            ("DailySignalModel", DailySignalModel),
            # ("MaCrossSignalModel", MaCrossSignalModel),  # Commented out in original
        ]
    
    def get_or_create(self, ts_code: str) -> dict[str, object] | None:
        """Get cached strategies for a stock or create new ones."""
        if ts_code in self._cache:
            return self._cache[ts_code]
        
        strategies = {}
        for name, cls in self._strategies:
            try:
                model = cls(ts_code)
                if model.df is not None and not model.df.empty:
                    strategies[name] = model
            except Exception:
                continue
        
        if strategies:
            self._cache[ts_code] = strategies
            return strategies
        return None
    
    def clear(self):
        """Clear cache to free memory."""
        self._cache.clear()


def process_stock_batch(
    stock_batch: list[str],
    trade_dates: list[str],
    batch_id: int
) -> list[dict[str, object]]:
    """Process a batch of stocks for all trade dates."""
    import os
    # Suppress stdout in worker processes
    sys.stdout = open(os.devnull, 'w')
    
    cache = StrategyCache()
    docs: list[dict[str, object]] = []
    
    for ts_code in stock_batch:
        strategies = cache.get_or_create(ts_code)
        if not strategies:
            continue
        
        for trade_date in trade_dates:
            for strategy_name, model in strategies.items():
                try:
                    signal = model.predict_date(trade_date)
                    if signal == "BUY":
                        docs.append({
                            "trading_date": trade_date,
                            "stock_code": ts_code,
                            "strategy": strategy_name,
                            "signal": signal,
                            "created_at": dt.datetime.now(dt.UTC),
                        })
                except Exception:
                    continue
    
    sys.stdout.close()
    sys.stdout = sys.__stdout__
    return docs


def process_single_date_optimized(
    trade_date: str,
    stock_list: list[str],
    workers: int = 4,
    batch_size: int = 100
) -> int:
    """Process a single date with parallel execution."""
    # Split stock list into batches
    batches = [
        stock_list[i:i + batch_size]
        for i in range(0, len(stock_list), batch_size)
    ]
    
    docs: list[dict[str, object]] = []
    completed = 0
    
    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(process_stock_batch, batch, [trade_date], idx): idx
            for idx, batch in enumerate(batches)
        }
        
        for future in as_completed(futures):
            batch_id = futures[future]
            try:
                batch_docs = future.result()
                docs.extend(batch_docs)
                completed += 1
                logger.debug(
                    "[%s/%s] Batch %s completed, docs so far=%s",
                    completed,
                    len(batches),
                    batch_id,
                    len(docs),
                )
            except Exception as exc:
                logger.exception("Batch %s failed: %s", batch_id, exc)
    
    # Insert into MongoDB
    collection = get_collection("daily_signal")
    delete_result = collection.delete_many({"trading_date": trade_date})
    if delete_result.deleted_count > 0:
        logger.info("deleted existing %s signals for %s", delete_result.deleted_count, trade_date)
    
    if docs:
        collection.insert_many(docs)
    
    logger.info("done trade_date=%s buy_signals=%s", trade_date, len(docs))
    return len(docs)


def process_date_range_parallel(
    start_date: str,
    end_date: str,
    workers: int = 4,
    batch_size: int = 100
) -> None:
    """Process a date range with parallel execution per date."""
    stock_list = list_stock_codes()
    if not stock_list:
        raise SystemExit("No stock_basic data available")
    
    logger.info("Loaded %s stocks", len(stock_list))
    
    trading_days = get_trading_days(start_date, end_date)
    logger.info("Found %s trading days", len(trading_days))

    progress = tqdm(trading_days, total=len(trading_days), desc="calculate_signal_optimized", unit="day", dynamic_ncols=True)
    for trade_date in progress:
        progress.set_postfix(date=trade_date)
        process_single_date_optimized(trade_date, stock_list, workers, batch_size)

    logger.info("All done! Processed %s trading days.", len(trading_days))


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    args = parse_args()
    
    if args.given_date:
        # Single date mode
        trade_date = normalize_date(args.given_date)
        if not is_trading_day(trade_date, exchange="SSE"):
            logger.info("%s is not a trading day, skipping...", trade_date)
            return
        stock_list = list_stock_codes()
        if not stock_list:
            raise SystemExit("No stock_basic data available")
        process_single_date_optimized(
            trade_date, stock_list, 
            workers=args.workers, batch_size=args.batch_size
        )
    else:
        # Date range mode
        if args.start_date and args.end_date:
            start_date = args.start_date
            end_date = args.end_date
        elif args.start_date:
            start_date = args.start_date
            end_date = dt.datetime.now().strftime("%Y%m%d")
            logger.info("--end-date not provided, using today: %s", end_date)
        elif args.end_date:
            start_date = "2020-01-01"
            end_date = args.end_date
        else:
            start_date = "2020-01-01"
            end_date = dt.datetime.now().strftime("%Y%m%d")
        
        process_date_range_parallel(
            start_date, end_date,
            workers=args.workers, batch_size=args.batch_size
        )


if __name__ == "__main__":
    main()
