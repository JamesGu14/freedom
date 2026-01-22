from __future__ import annotations

import pandas as pd
from pathlib import Path

from app.core.config import settings


def get_parquet_path(table: str, trade_date: str | None = None) -> Path:
    """获取 Parquet 文件路径"""
    base_dir = settings.data_dir / "raw" / table
    if trade_date:
        # 按日期分区：daily/trade_date=20240101/part-0.parquet
        return base_dir / f"trade_date={trade_date}" / "part-0.parquet"
    else:
        # 不分区的表：stock_basic/part-0.parquet
        return base_dir / "part-0.parquet"


def write_daily_to_parquet(df: pd.DataFrame) -> int:
    """将 daily 数据写入 Parquet（按日期分区）"""
    if df.empty:
        return 0

    if "trade_date" not in df.columns:
        return 0

    written = 0
    for trade_date, group_df in df.groupby("trade_date"):
        trade_date_str = str(trade_date)
        parquet_path = get_parquet_path("daily", trade_date_str)
        parquet_path.parent.mkdir(parents=True, exist_ok=True)

        # 如果文件已存在，读取并去重合并
        if parquet_path.exists():
            try:
                existing_df = pd.read_parquet(parquet_path)
                # 合并并去重（保留新数据）
                combined = pd.concat([existing_df, group_df])
                combined = combined.drop_duplicates(
                    subset=["ts_code", "trade_date"], keep="last"
                )
                combined.to_parquet(parquet_path, index=False)
            except Exception:
                # 如果读取失败，直接覆盖
                group_df.to_parquet(parquet_path, index=False)
        else:
            group_df.to_parquet(parquet_path, index=False)

        written += len(group_df)

    return written


def write_adj_factor_to_parquet(df: pd.DataFrame) -> int:
    """将 adj_factor 数据写入 Parquet（按日期分区）"""
    if df.empty:
        return 0

    if "trade_date" not in df.columns:
        return 0

    written = 0
    for trade_date, group_df in df.groupby("trade_date"):
        trade_date_str = str(trade_date)
        parquet_path = get_parquet_path("adj_factor", trade_date_str)
        parquet_path.parent.mkdir(parents=True, exist_ok=True)

        if parquet_path.exists():
            try:
                existing_df = pd.read_parquet(parquet_path)
                combined = pd.concat([existing_df, group_df])
                combined = combined.drop_duplicates(
                    subset=["ts_code", "trade_date"], keep="last"
                )
                combined.to_parquet(parquet_path, index=False)
            except Exception:
                group_df.to_parquet(parquet_path, index=False)
        else:
            group_df.to_parquet(parquet_path, index=False)

        written += len(group_df)

    return written


def write_stock_basic_to_parquet(df: pd.DataFrame) -> int:
    """将 stock_basic 数据写入 Parquet（不分区）"""
    if df.empty:
        return 0

    parquet_path = get_parquet_path("stock_basic")
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(parquet_path, index=False)
    return df.shape[0]


def get_parquet_pattern(table: str) -> str:
    """获取 Parquet 文件的 glob 模式"""
    base_dir = settings.data_dir / "raw" / table
    if table in ("daily", "adj_factor"):
        # 按日期分区的表
        pattern = str(base_dir / "trade_date=*" / "*.parquet")
    else:
        # 不分区的表
        pattern = str(base_dir / "*.parquet")
    return pattern

