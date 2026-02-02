#!/usr/bin/env python3
"""
Optimized signal calculation script with strategy caching per stock.
"""
from __future__ import annotations
from scripts.strategy.third import DailySignalModel

import argparse
import datetime as dt
import sys
import time
from pathlib import Path
from typing import ClassVar

import tushare as ts

SCRIPT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(SCRIPT_ROOT))

from app.core.config import settings  # noqa: E402
from app.data.mongo import get_collection  # noqa: E402
from app.data.mongo_stock import list_stock_codes  # noqa: E402
from scripts.strategy.first import MaCrossSignalModel  # noqa: E402
from scripts.strategy.second import EarlyBreakoutSignalModel  # noqa: E402


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


def get_default_date_range() -> tuple[str, str]:
    """返回默认日期范围：2020-01-01 到今天"""
    today = dt.datetime.now().strftime("%Y-%m-%d")
    return "2020-01-01", today


def normalize_date(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("given_date is required")
    if "-" in value:
        return dt.datetime.strptime(value, "%Y-%m-%d").strftime("%Y%m%d")
    if len(value) == 8:
        return value
    raise ValueError("given_date must be YYYYMMDD or YYYY-MM-DD")


def is_trading_day(pro: ts.pro_api, trade_date: str) -> bool:
    df = pro.trade_cal(exchange="SSE", start_date=trade_date, end_date=trade_date, fields="is_open")
    if df is None or df.empty:
        return False
    return int(df.iloc[0]["is_open"]) == 1


ALLOWED_PREFIXES = ("000", "600", "300", "688")


def load_stock_list() -> list[str]:
    """Load stock codes and filter by allowed prefixes."""
    all_codes = list_stock_codes()
    filtered = [code for code in all_codes if code.startswith(ALLOWED_PREFIXES)]
    return filtered


def get_trading_days(start_date: str, end_date: str) -> list[str]:
    """获取日期区间内的所有交易日"""
    if not settings.tushare_token:
        raise SystemExit("TUSHARE_TOKEN is required")

    pro = ts.pro_api(settings.tushare_token)
    # 转换为 YYYYMMDD 格式
    start = normalize_date(start_date)
    end = normalize_date(end_date)

    df = pro.trade_cal(exchange="SSE", start_date=start, end_date=end, fields="cal_date,is_open")
    if df is None or df.empty:
        return []

    # 筛选交易日
    trading_days = df[df["is_open"] == 1]["cal_date"].tolist()
    return [str(date) for date in trading_days]


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
    if not settings.tushare_token:
        raise SystemExit("TUSHARE_TOKEN is required")

    pro = ts.pro_api(settings.tushare_token)
    if not is_trading_day(pro, trade_date):
        print(f"{trade_date} is not a trading day, skipping...")
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
            print(f"[{idx}/{len(stock_list)}] docs={len(docs)} "
                  f"rate={rate:.1f}stocks/s ETA={remaining:.0f}s")

    # 显示统计信息
    total_time = time.perf_counter() - start_time
    print(f"Processing completed: {len(stock_list)} stocks in {total_time:.1f}s "
          f"({len(stock_list)/total_time:.1f} stocks/s)")

    collection = get_collection("daily_signal")
    
    # 删除该日期的已有数据，避免重复
    delete_result = collection.delete_many({"trading_date": trade_date})
    if delete_result.deleted_count > 0:
        print(f"deleted existing {delete_result.deleted_count} signals for {trade_date}")
    
    if docs:
        collection.insert_many(docs)

    buy_count = len(docs)
    print(f"done trade_date={trade_date} buy_signals={buy_count}")


def main() -> None:
    args = parse_args()

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
            print(f"--end-date not provided, using today: {end_date}")
        elif args.end_date:
            # 只提供了 end-date，start-date 使用默认值
            start_date = "2020-01-01"
            end_date = args.end_date
        else:
            # 都没提供，使用默认范围：2020-01-01 到今天
            start_date = "2020-01-01"
            end_date = dt.datetime.now().strftime("%Y%m%d")

        print(f"Getting trading days from {start_date} to {end_date}...")
        trading_days = get_trading_days(start_date, end_date)
        print(f"Found {len(trading_days)} trading days")

        # 预加载股票列表（复用）
        print("Loading stock list...")
        stock_list = load_stock_list()
        if not stock_list:
            raise SystemExit("No stock_basic data available")
        print(f"Loaded {len(stock_list)} stocks")

        for idx, trade_date in enumerate(trading_days, start=1):
            print(f"\n[{idx}/{len(trading_days)}] Processing {trade_date}...")
            try:
                process_single_date(trade_date, stock_list=stock_list)
            except Exception as exc:
                print(f"Error processing {trade_date}: {exc}")
                import traceback
                traceback.print_exc()
                continue

        # 清理缓存
        clear_strategy_cache()
        print(f"\nAll done! Processed {len(trading_days)} trading days.")


if __name__ == "__main__":
    main()
