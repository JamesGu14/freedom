#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

import tushare as ts

SCRIPT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(SCRIPT_ROOT))

from app.core.config import settings  # noqa: E402
from app.data.duckdb_store import get_connection  # noqa: E402
from app.data.mongo import get_collection  # noqa: E402
from scripts.strategy.first import MaCrossSignalModel  # noqa: E402
from scripts.strategy.second import EarlyBreakoutSignalModel  # noqa: E402
from scripts.strategy.third import DailySignalModel


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Calculate daily signals for a given trading date and store BUY signals."
    )
    parser.add_argument("--given-date", type=str, required=False, help="YYYYMMDD or YYYY-MM-DD")
    parser.add_argument("--start-date", type=str, required=False, help="Start date: YYYYMMDD or YYYY-MM-DD")
    parser.add_argument("--end-date", type=str, required=False, help="End date: YYYYMMDD or YYYY-MM-DD")
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


def is_trading_day(pro: ts.pro_api, trade_date: str) -> bool:
    df = pro.trade_cal(exchange="SSE", start_date=trade_date, end_date=trade_date, fields="is_open")
    if df is None or df.empty:
        return False
    return int(df.iloc[0]["is_open"]) == 1


def load_stock_list() -> list[str]:
    with get_connection() as con:
        rows = con.execute("SELECT ts_code FROM stock_basic ORDER BY ts_code").fetchall()
    return [row[0] for row in rows]


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


def process_single_date(trade_date: str) -> None:
    """处理单个日期的信号计算"""
    if not settings.tushare_token:
        raise SystemExit("TUSHARE_TOKEN is required")
    
    pro = ts.pro_api(settings.tushare_token)
    if not is_trading_day(pro, trade_date):
        print(f"{trade_date} is not a trading day, skipping...")
        return
    
    stock_list = load_stock_list()
    if not stock_list:
        raise SystemExit("No stock_basic data available")
    
    strategies = [
        # ("MaCrossSignalModel", MaCrossSignalModel),
        ("EarlyBreakoutSignalModel", EarlyBreakoutSignalModel),
        ("DailySignalModel", DailySignalModel),
    ]
    
    docs: list[dict[str, object]] = []
    for idx, ts_code in enumerate(stock_list, start=1):
        for strategy_name, strategy_cls in strategies:
            try:
                model = strategy_cls(ts_code)
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
        if idx % 200 == 0:
            print(f"processed {idx}/{len(stock_list)}, current docs count: {len(docs)}")
    
    if docs:
        collection = get_collection("daily_signal")
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
    else:
        # 验证日期区间参数
        if (args.start_date and not args.end_date) or (args.end_date and not args.start_date):
            raise SystemExit("--start-date and --end-date must be provided together")
        
        # 确定日期区间
        if args.start_date and args.end_date:
            start_date = args.start_date
            end_date = args.end_date
        else:
            # 默认日期区间
            start_date = "2020-01-01"
            end_date = "2025-01-09"
        
        print(f"Getting trading days from {start_date} to {end_date}...")
        trading_days = get_trading_days(start_date, end_date)
        print(f"Found {len(trading_days)} trading days")
        
        for idx, trade_date in enumerate(trading_days, start=1):
            print(f"\n[{idx}/{len(trading_days)}] Processing {trade_date}...")
            try:
                process_single_date(trade_date)
            except Exception as exc:
                print(f"Error processing {trade_date}: {exc}")
                import traceback
                traceback.print_exc()
                continue
        
        print(f"\nAll done! Processed {len(trading_days)} trading days.")


if __name__ == "__main__":
    main()
