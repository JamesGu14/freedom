#!/usr/bin/env python3
"""
增量计算技术指标脚本 - 只计算新日期的指标并追加到现有数据
原理：加载足够的历史数据来计算指标，但只保存新日期范围的结果
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
from scripts.one_time.calculate_indicators import IndicatorCalculator


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="追加计算技术指标")
    parser.add_argument("--start-date", type=str, required=True, help="开始日期: YYYYMMDD")
    parser.add_argument("--end-date", type=str, required=True, help="结束日期: YYYYMMDD")
    parser.add_argument("--lookback", type=int, default=100, help="回退天数用于计算指标")
    return parser.parse_args()


def normalize_date(date_str: str) -> str:
    return date_str.replace("-", "")


def load_daily_with_lookback(ts_code: str, start_date: str, lookback_days: int = 100) -> pd.DataFrame:
    """加载日线数据，包含 start_date 之前 lookback_days 天的历史"""
    import datetime as dt
    
    start_dt = dt.datetime.strptime(start_date, "%Y%m%d")
    lookback_start = start_dt - dt.timedelta(days=lookback_days)
    lookback_start_str = lookback_start.strftime("%Y%m%d")
    
    daily_root = settings.data_dir / "raw" / "daily" / f"ts_code={ts_code}"
    if not daily_root.exists():
        return pd.DataFrame()

    part_glob = str(daily_root / "year=*/part-*.parquet")
    
    query = (
        f"SELECT ts_code, trade_date, open, high, low, close, vol, amount "
        f"FROM read_parquet(?) WHERE ts_code = ? AND trade_date >= ? ORDER BY trade_date"
    )
    
    with get_connection() as con:
        try:
            df = con.execute(query, [part_glob, ts_code, lookback_start_str]).fetchdf()
        except Exception as exc:
            return pd.DataFrame()

    if not df.empty:
        df["trade_date"] = pd.to_datetime(df["trade_date"], format="%Y%m%d")
        df = df.sort_values("trade_date").reset_index(drop=True)
    return df


def save_indicators_append(df: pd.DataFrame) -> int:
    """追加保存指标数据到 parquet 文件"""
    if df.empty:
        return 0

    features_base = settings.data_dir / "features" / "indicators"
    features_base.mkdir(parents=True, exist_ok=True)

    data = df.copy()
    if pd.api.types.is_datetime64_any_dtype(data["trade_date"]):
        data["trade_date"] = data["trade_date"].dt.strftime("%Y%m%d")
    data["year"] = data["trade_date"].str[:4]

    total_saved = 0
    for (ts_code, year), group in data.groupby(["ts_code", "year"], sort=False):
        partition_dir = features_base / f"ts_code={ts_code}" / f"year={year}"
        partition_dir.mkdir(parents=True, exist_ok=True)
        new_rows = group.drop(columns=["year"])
        part_path = partition_dir / f"part-{uuid.uuid4().hex}.parquet"
        new_rows.to_parquet(part_path, index=False, engine="pyarrow")
        total_saved += len(new_rows)

    return total_saved


def main():
    args = parse_args()
    start_date = normalize_date(args.start_date)
    end_date = normalize_date(args.end_date)
    lookback = args.lookback
    
    if start_date > end_date:
        raise SystemExit(f"Error: start_date ({start_date}) > end_date ({end_date})")
    
    print(f"追加计算指标: {start_date} 到 {end_date} (回退{lookback}天计算)")
    
    stock_list = list_stock_codes()
    calculator = IndicatorCalculator()
    
    total_start = time.perf_counter()
    total_new = 0
    
    for idx, ts_code in enumerate(stock_list, 1):
        try:
            # 1. 加载包含历史数据的日线
            daily_df = load_daily_with_lookback(ts_code, start_date, lookback)
            if daily_df.empty or len(daily_df) < 2:
                continue
            
            # 2. 计算所有指标（基于完整历史数据）
            indicators = calculator.calculate_all(daily_df)
            
            # 3. 筛选出指定日期范围的新指标
            indicators["trade_date_str"] = indicators["trade_date"].dt.strftime("%Y%m%d")
            mask = (indicators["trade_date_str"] >= start_date) & (indicators["trade_date_str"] <= end_date)
            new_indicators = indicators[mask].drop(columns=["trade_date_str"])
            
            if new_indicators.empty:
                continue
            
            # 4. 将 trade_date 转回 datetime 用于保存
            if not pd.api.types.is_datetime64_any_dtype(new_indicators["trade_date"]):
                new_indicators["trade_date"] = pd.to_datetime(new_indicators["trade_date"])
            
            # 5. 追加保存（不删除任何现有数据）
            saved = save_indicators_append(new_indicators)
            total_new += saved
            
            if idx % 500 == 0:
                elapsed = time.perf_counter() - total_start
                print(f"[{idx}/{len(stock_list)}] processed, new_rows={total_new}, elapsed={elapsed:.1f}s")
            
        except Exception as exc:
            print(f"[{idx}/{len(stock_list)}] {ts_code} failed: {exc}")
    
    total_elapsed = time.perf_counter() - total_start
    print(f"\n完成: {len(stock_list)} 只股票, 新增 {total_new} 行指标")
    print(f"耗时: {total_elapsed:.1f}s ({total_elapsed/60:.1f}分钟)")


if __name__ == "__main__":
    main()
