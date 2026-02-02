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
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from functools import lru_cache
from pathlib import Path

import pandas as pd

SCRIPT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(SCRIPT_ROOT))

from app.core.config import settings
from app.data.mongo import get_collection
from app.data.mongo_stock import list_stock_codes
from scripts.strategy.first import MaCrossSignalModel
from scripts.strategy.second import EarlyBreakoutSignalModel
from scripts.strategy.third import DailySignalModel


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
    import tushare as ts
    
    if not settings.tushare_token:
        raise SystemExit("TUSHARE_TOKEN is required")
    
    pro = ts.pro_api(settings.tushare_token)
    start = normalize_date(start_date)
    end = normalize_date(end_date)
    
    df = pro.trade_cal(exchange="SSE", start_date=start, end_date=end, fields="cal_date,is_open")
    if df is None or df.empty:
        return []
    
    trading_days = df[df["is_open"] == 1]["cal_date"].tolist()
    return [str(d) for d in trading_days]


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
                print(f"[{completed}/{len(batches)}] Batch {batch_id} completed, docs so far: {len(docs)}")
            except Exception as exc:
                print(f"Batch {batch_id} failed: {exc}")
    
    # Insert into MongoDB
    collection = get_collection("daily_signal")
    delete_result = collection.delete_many({"trading_date": trade_date})
    if delete_result.deleted_count > 0:
        print(f"deleted existing {delete_result.deleted_count} signals for {trade_date}")
    
    if docs:
        collection.insert_many(docs)
    
    print(f"done trade_date={trade_date} buy_signals={len(docs)}")
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
    
    print(f"Loaded {len(stock_list)} stocks")
    
    trading_days = get_trading_days(start_date, end_date)
    print(f"Found {len(trading_days)} trading days")
    
    for idx, trade_date in enumerate(trading_days, start=1):
        print(f"\n[{idx}/{len(trading_days)}] Processing {trade_date}...")
        process_single_date_optimized(trade_date, stock_list, workers, batch_size)
    
    print(f"\nAll done! Processed {len(trading_days)} trading days.")


def main() -> None:
    args = parse_args()
    
    if args.given_date:
        # Single date mode
        trade_date = normalize_date(args.given_date)
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
            print(f"--end-date not provided, using today: {end_date}")
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
