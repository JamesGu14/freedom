#!/usr/bin/env python3
"""
Optimized signal calculation script with strategy caching per stock.
"""
from __future__ import annotations
from scripts.strategy.third import DailySignalModel

import argparse
import datetime as dt
import logging
import sys
import time
from pathlib import Path

from tqdm import tqdm

SCRIPT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(SCRIPT_ROOT))

from app.data.mongo import get_collection  # noqa: E402
from app.data.mongo_trade_calendar import is_trading_day  # noqa: E402
from app.data.mongo_stock import list_stock_codes  # noqa: E402
from scripts.strategy.second import EarlyBreakoutSignalModel  # noqa: E402

logger = logging.getLogger(__name__)

# Global strategy cache: {ts_code: {strategy_name: model_instance}}
_strategy_cache: dict[str, dict[str, object]] = {}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Calculate daily signals for a given trading date and store BUY signals."
    )
    parser.add_argument("--given-date", type=str, required=False, help="YYYYMMDD or YYYY-MM-DD")
    parser.add_argument("--start-date", type=str, required=False, help="Start date: YYYYMMDD or YYYY-MM-DD")
    parser.add_argument("--end-date", type=str, required=False, help="End date: YYYYMMDD or YYYY-MM-DD (default: today)")
    return parser.parse_args()


def normalize_date(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("given_date is required")
    if "-" in value:
        return dt.datetime.strptime(value, "%Y-%m-%d").strftime("%Y%m%d")
    if len(value) == 8:
        return value
    raise ValueError("given_date must be YYYYMMDD or YYYY-MM-DD")


ALLOWED_PREFIXES = ("000", "600", "300", "688")


def build_date_list(start_date: str, end_date: str) -> list[str]:
    start = dt.datetime.strptime(start_date, "%Y%m%d")
    end = dt.datetime.strptime(end_date, "%Y%m%d")
    if start > end:
        raise ValueError("start_date cannot be after end_date")
    days = []
    cur = start
    while cur <= end:
        days.append(cur.strftime("%Y%m%d"))
        cur += dt.timedelta(days=1)
    return days


def load_stock_list() -> list[str]:
    """Load stock codes and filter by allowed prefixes."""
    all_codes = list_stock_codes()
    filtered = [code for code in all_codes if code.startswith(ALLOWED_PREFIXES)]
    return filtered


def get_trading_days(start_date: str, end_date: str) -> list[str]:
    """获取日期区间内的所有交易日"""
    start = normalize_date(start_date)
    end = normalize_date(end_date)
    return [date for date in build_date_list(start, end) if is_trading_day(date, exchange="SSE")]


def get_or_create_strategy(ts_code: str, strategy_name: str, strategy_cls) -> object | None:
    """Get cached strategy or create new one."""
    global _strategy_cache
    
    if ts_code not in _strategy_cache:
        _strategy_cache[ts_code] = {}
    
    if strategy_name not in _strategy_cache[ts_code]:
        try:
            model = strategy_cls(ts_code)
            if model.df is None or model.df.empty:
                return None
            _strategy_cache[ts_code][strategy_name] = model
        except Exception:
            return None
    
    return _strategy_cache[ts_code].get(strategy_name)


def clear_strategy_cache() -> None:
    """Clear strategy cache to free memory."""
    global _strategy_cache
    _strategy_cache.clear()


def process_single_date(trade_date: str, stock_list: list[str] | None = None) -> None:
    """处理单个日期的信号计算（带缓存优化）"""
    if not is_trading_day(trade_date, exchange="SSE"):
        logger.info("%s is not a trading day, skipping...", trade_date)
        return

    if stock_list is None:
        stock_list = load_stock_list()
    if not stock_list:
        raise SystemExit("No stock_basic data available")

    strategies = [
        # ("MaCrossSignalModel", MaCrossSignalModel),
        ("EarlyBreakoutSignalModel", EarlyBreakoutSignalModel),
        ("DailySignalModel", DailySignalModel),
    ]

    docs: list[dict[str, object]] = []
    start_time = time.perf_counter()
    
    for idx, ts_code in enumerate(stock_list, start=1):
        for strategy_name, strategy_cls in strategies:
            model = get_or_create_strategy(ts_code, strategy_name, strategy_cls)
            if model is None:
                continue
            try:
                signal = model.predict_date(trade_date)
            except Exception:
                continue
            if signal == "BUY":
                docs.append(
                    {
                        "trading_date": trade_date,
                        "stock_code": ts_code,
                        "strategy": strategy_name,
                        "signal": signal,
                        "created_at": dt.datetime.now(dt.UTC),
                    }
                )
        
        if idx % 500 == 0:
            elapsed = time.perf_counter() - start_time
            rate = idx / elapsed if elapsed > 0 else 0
            remaining = (len(stock_list) - idx) / rate if rate > 0 else 0
            logger.debug(
                "[%s/%s] docs=%s rate=%.1f stocks/s ETA=%.0fs",
                idx,
                len(stock_list),
                len(docs),
                rate,
                remaining,
            )

    # 显示统计信息
    total_time = time.perf_counter() - start_time
    logger.info(
        "Processing completed: %s stocks in %.1fs (%.1f stocks/s)",
        len(stock_list),
        total_time,
        len(stock_list) / total_time if total_time > 0 else 0,
    )

    collection = get_collection("daily_signal")
    
    # 删除该日期的已有数据，避免重复
    delete_result = collection.delete_many({"trading_date": trade_date})
    if delete_result.deleted_count > 0:
        logger.info("deleted existing %s signals for %s", delete_result.deleted_count, trade_date)
    
    if docs:
        collection.insert_many(docs)

    buy_count = len(docs)
    logger.info("done trade_date=%s buy_signals=%s", trade_date, buy_count)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    args = parse_args()

    # 验证日期范围
    if args.start_date and args.end_date:
        start_normalized = normalize_date(args.start_date)
        end_normalized = normalize_date(args.end_date)
        if start_normalized > end_normalized:
            raise SystemExit(
                f"Error: start_date ({args.start_date}) cannot be after end_date ({args.end_date}). "
                f"Please check your date arguments."
            )

    # 如果提供了 --given-date，只处理单个日期
    if args.given_date:
        given_date = args.given_date
        trade_date = normalize_date(given_date)
        process_single_date(trade_date)
        # 清理缓存
        clear_strategy_cache()
    else:
        # 确定日期区间
        if args.start_date and args.end_date:
            # 同时提供了起止日期
            start_date = args.start_date
            end_date = args.end_date
        elif args.start_date:
            # 只提供了 start-date，end-date 默认为今天
            start_date = args.start_date
            end_date = dt.datetime.now().strftime("%Y%m%d")
            logger.info("--end-date not provided, using today: %s", end_date)
        elif args.end_date:
            # 只提供了 end-date，start-date 使用默认值
            start_date = "2020-01-01"
            end_date = args.end_date
        else:
            # 都没提供，使用默认范围：2020-01-01 到今天
            start_date = "2020-01-01"
            end_date = dt.datetime.now().strftime("%Y%m%d")

        logger.info("Getting trading days from %s to %s...", start_date, end_date)
        trading_days = get_trading_days(start_date, end_date)
        logger.info("Found %s trading days", len(trading_days))

        # 预加载股票列表（复用）
        logger.info("Loading stock list...")
        stock_list = load_stock_list()
        if not stock_list:
            raise SystemExit("No stock_basic data available")
        logger.info("Loaded %s stocks", len(stock_list))

        progress = tqdm(trading_days, total=len(trading_days), desc="calculate_signal", unit="day", dynamic_ncols=True)
        for trade_date in progress:
            progress.set_postfix(date=trade_date)
            try:
                process_single_date(trade_date, stock_list=stock_list)
            except Exception as exc:
                logger.exception("Error processing %s: %s", trade_date, exc)
                continue

        # 清理缓存
        clear_strategy_cache()
        logger.info("All done! Processed %s trading days.", len(trading_days))


if __name__ == "__main__":
    main()
