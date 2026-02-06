#!/usr/bin/env python3
"""
增量计算技术指标脚本 - 只计算新日期的指标并追加到现有数据
"""
from __future__ import annotations

import argparse
import time
import uuid
from pathlib import Path
import sys

import pandas as pd

SCRIPT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(SCRIPT_ROOT))

from app.core.config import settings
from app.data.duckdb_store import get_connection
from app.data.mongo_stock import list_stock_codes
from scripts.one_time.calculate_indicators import IndicatorCalculator, save_indicators


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="增量计算技术指标（追加模式）")
    parser.add_argument("--start-date", type=str, required=True, help="开始日期: YYYYMMDD")
    parser.add_argument("--end-date", type=str, required=True, help="结束日期: YYYYMMDD")
    parser.add_argument("--lookback-days", type=int, default=100, 
                        help="向前加载多少天的历史数据用于计算指标（默认100天）")
    return parser.parse_args()


def normalize_date(date_str: str) -> str:
    """Normalize date string to YYYYMMDD format."""
    return date_str.replace("-", "")


def load_daily_data_with_lookback(ts_code: str, start_date: str, end_date: str, 
                                   lookback_days: int = 100) -> pd.DataFrame:
    """加载日线数据，包含 start_date 之前 lookback_days 天的历史数据"""
    import datetime as dt
    
    # 计算需要加载的历史数据起始日期
    start_dt = dt.datetime.strptime(start_date, "%Y%m%d")
    lookback_start = start_dt - dt.timedelta(days=lookback_days)
    lookback_start_str = lookback_start.strftime("%Y%m%d")
    
    daily_root = settings.data_dir / "raw" / "daily" / f"ts_code={ts_code}"
    if not daily_root.exists():
        return pd.DataFrame()

    part_glob = str(daily_root / "year=*/part-*.parquet")
    
    query = (
        f"SELECT ts_code, trade_date, open, high, low, close, vol, amount "
        f"FROM read_parquet(?) WHERE ts_code = ? AND trade_date >= ? AND trade_date <= ? "
        f"ORDER BY trade_date"
    )
    
    with get_connection() as con:
        try:
            df = con.execute(query, [part_glob, ts_code, lookback_start_str, end_date]).fetchdf()
        except Exception as exc:
            print(f"Error loading data for {ts_code}: {exc}")
            return pd.DataFrame()

    if not df.empty:
        df["trade_date"] = pd.to_datetime(df["trade_date"], format="%Y%m%d")
        df = df.sort_values("trade_date").reset_index(drop=True)
    return df


def load_existing_indicators(ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
    """加载指定日期范围外的现有指标数据"""
    features_base = settings.data_dir / "features" / "indicators"
    stock_dir = features_base / f"ts_code={ts_code}"
    
    if not stock_dir.exists():
        return pd.DataFrame()
    
    all_data = []
    for year_dir in stock_dir.iterdir():
        if not year_dir.is_dir():
            continue
        for parquet_file in year_dir.glob("*.parquet"):
            try:
                df = pd.read_parquet(parquet_file)
                all_data.append(df)
            except Exception as e:
                print(f"Error reading {parquet_file}: {e}")
    
    if not all_data:
        return pd.DataFrame()
    
    combined = pd.concat(all_data, ignore_index=True)
    
    # 确保 trade_date 是字符串格式
    combined["trade_date"] = combined["trade_date"].astype(str)
    
    # 过滤掉指定日期范围内的数据（这些会被重新计算）
    mask = pd.Series([True] * len(combined))
    if start_date:
        mask &= combined["trade_date"] < start_date
    if end_date:
        mask &= combined["trade_date"] > end_date
    
    return combined[mask]


def delete_and_save_indicators(ts_code: str, existing_df: pd.DataFrame, 
                                new_df: pd.DataFrame) -> int:
    """删除旧数据并保存合并后的数据"""
    import shutil
    
    features_base = settings.data_dir / "features" / "indicators"
    stock_dir = features_base / f"ts_code={ts_code}"
    
    # 删除该股票的所有旧指标数据
    if stock_dir.exists():
        shutil.rmtree(stock_dir)
    
    # 合并现有数据和新数据
    if existing_df.empty:
        combined = new_df
    elif new_df.empty:
        combined = existing_df
    else:
        combined = pd.concat([existing_df, new_df], ignore_index=True)
        combined = combined.drop_duplicates(subset=["ts_code", "trade_date"], keep="last")
        combined = combined.sort_values("trade_date").reset_index(drop=True)
    
    if combined.empty:
        return 0
    
    return save_indicators(combined)


def main() -> None:
    """Main function to calculate indicators incrementally."""
    args = parse_args()
    start_date = normalize_date(args.start_date)
    end_date = normalize_date(args.end_date)
    lookback_days = args.lookback_days
    
    # 验证日期范围
    if start_date > end_date:
        raise SystemExit(f"Error: start_date ({start_date}) cannot be after end_date ({end_date})")
    
    print(f"增量计算指标: {start_date} 到 {end_date}, 回退 {lookback_days} 天加载历史数据")
    
    total_start = time.perf_counter()
    stock_list = list_stock_codes()
    if not stock_list:
        raise SystemExit("No stock_basic data available")

    calculator = IndicatorCalculator()
    total_new_rows = 0
    total_existing_rows = 0

    for idx, ts_code in enumerate(stock_list, start=1):
        stock_start = time.perf_counter()
        try:
            # 1. 加载现有指标数据（指定日期范围外的）
            existing_df = load_existing_indicators(ts_code, start_date, end_date)
            total_existing_rows += len(existing_df)
            
            # 2. 加载日线数据（包含历史数据用于计算）
            daily_df = load_daily_data_with_lookback(ts_code, start_date, end_date, lookback_days)
            if daily_df.empty:
                print(f"[{idx}/{len(stock_list)}] {ts_code} skipped (no daily data)")
                continue
            
            # 3. 计算指标（基于包含历史数据的日线）
            all_indicators = calculator.calculate_all(daily_df)
            
            # 4. 只保留指定日期范围的指标
            if pd.api.types.is_datetime64_any_dtype(all_indicators["trade_date"]):
                all_indicators["trade_date_str"] = all_indicators["trade_date"].dt.strftime("%Y%m%d")
            else:
                all_indicators["trade_date_str"] = all_indicators["trade_date"].astype(str)
            
            mask = (all_indicators["trade_date_str"] >= start_date) & \
                   (all_indicators["trade_date_str"] <= end_date)
            new_indicators = all_indicators[mask].copy()
            
            if new_indicators.empty:
                print(f"[{idx}/{len(stock_list)}] {ts_code} no new indicators in date range")
                continue
            
            # 删除临时列
            if "trade_date_str" in new_indicators.columns:
                new_indicators = new_indicators.drop(columns=["trade_date_str"])
            if "trade_date_str" in all_indicators.columns:
                all_indicators = all_indicators.drop(columns=["trade_date_str"])
            
            # 5. 合并并保存
            saved_count = delete_and_save_indicators(ts_code, existing_df, new_indicators)
            total_new_rows += len(new_indicators)
            
            stock_elapsed = time.perf_counter() - stock_start
            print(
                f"[{idx}/{len(stock_list)}] {ts_code} "
                f"existing={len(existing_df)} new={len(new_indicators)} "
                f"saved={saved_count} elapsed={stock_elapsed:.2f}s"
            )
            
        except Exception as exc:
            stock_elapsed = time.perf_counter() - stock_start
            print(f"[{idx}/{len(stock_list)}] {ts_code} failed: {exc} elapsed={stock_elapsed:.2f}s")

    total_elapsed = time.perf_counter() - total_start
    print(f"\nTotal: processed {len(stock_list)} stocks")
    print(f"Existing rows preserved: {total_existing_rows}")
    print(f"New rows calculated: {total_new_rows}")
    print(f"Elapsed: {total_elapsed:.2f}s ({total_elapsed/60:.2f} minutes)")


if __name__ == "__main__":
    main()
