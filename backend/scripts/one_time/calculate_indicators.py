#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import time
import uuid
from pathlib import Path
import sys

import pandas as pd

SCRIPT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(SCRIPT_ROOT))

from app.core.config import settings
from app.data.duckdb_store import get_connection
from app.data.mongo_stock import list_stock_codes


class IndicatorCalculator:
    """Technical indicator calculator class."""

    @staticmethod
    def ma(df: pd.DataFrame, period: int, price_col: str = "close") -> pd.Series:
        """Calculate Moving Average."""
        return df[price_col].rolling(window=period, min_periods=1).mean()

    @staticmethod
    def macd(
        df: pd.DataFrame,
        fast: int = 12,
        slow: int = 26,
        signal: int = 9,
        price_col: str = "close",
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate MACD (Moving Average Convergence Divergence).
        Returns: (macd, signal, histogram)
        """
        ema_fast = df[price_col].ewm(span=fast, adjust=False).mean()
        ema_slow = df[price_col].ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram

    @staticmethod
    def rsi(df: pd.DataFrame, period: int = 14, price_col: str = "close") -> pd.Series:
        """Calculate RSI (Relative Strength Index)."""
        delta = df[price_col].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi.fillna(50)  # Fill NaN with neutral value 50

    @staticmethod
    def kdj(
        df: pd.DataFrame,
        period: int = 9,
        k_period: int = 3,
        d_period: int = 3,
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate KDJ indicator.
        Returns: (K, D, J)
        """
        low_min = df["low"].rolling(window=period, min_periods=1).min()
        high_max = df["high"].rolling(window=period, min_periods=1).max()
        rsv = (df["close"] - low_min) / (high_max - low_min) * 100
        rsv = rsv.fillna(50)  # Fill NaN with neutral value

        k = rsv.ewm(alpha=1 / k_period, adjust=False).mean()
        d = k.ewm(alpha=1 / d_period, adjust=False).mean()
        j = 3 * k - 2 * d
        return k, d, j

    @staticmethod
    def boll(
        df: pd.DataFrame,
        period: int = 20,
        std_dev: float = 2.0,
        price_col: str = "close",
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Bollinger Bands.
        Returns: (upper, middle, lower)
        """
        middle = df[price_col].rolling(window=period, min_periods=1).mean()
        std = df[price_col].rolling(window=period, min_periods=1).std()
        upper = middle + (std * std_dev)
        lower = middle - (std * std_dev)
        return upper, middle, lower

    @classmethod
    def calculate_all(cls, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate all indicators and return DataFrame with results."""
        if df.empty:
            return df

        result = df[["ts_code", "trade_date"]].copy()

        # MA indicators
        for period in [5, 10, 20, 30, 60, 120, 200, 250, 500]:
            result[f"ma{period}"] = cls.ma(df, period)

        # MACD
        macd_line, signal_line, histogram = cls.macd(df)
        result["macd"] = macd_line
        result["macd_signal"] = signal_line
        result["macd_hist"] = histogram

        # RSI
        result["rsi"] = cls.rsi(df)

        # KDJ
        k, d, j = cls.kdj(df)
        result["kdj_k"] = k
        result["kdj_d"] = d
        result["kdj_j"] = j

        # BOLL
        boll_upper, boll_middle, boll_lower = cls.boll(df)
        result["boll_upper"] = boll_upper
        result["boll_middle"] = boll_middle
        result["boll_lower"] = boll_lower

        return result


def load_stock_list() -> list[str]:
    """Load all stock codes from MongoDB."""
    try:
        codes = list_stock_codes()
    except Exception as exc:
        raise SystemExit(f"failed to load stock_basic from MongoDB: {exc}") from exc
    if not codes:
        raise SystemExit("No stock_basic data available in MongoDB")
    return codes


def load_daily_data(ts_code: str, start_date: str | None = None, end_date: str | None = None) -> pd.DataFrame:
    """Load daily data for a stock from parquet files."""
    daily_root = settings.data_dir / "raw" / "daily" / f"ts_code={ts_code}"
    if not daily_root.exists():
        return pd.DataFrame()

    part_glob = str(daily_root / "year=*/part-*.parquet")
    
    # Build query with optional date filters
    where_clauses = ["ts_code = ?"]
    params = [part_glob, ts_code]
    
    if start_date:
        where_clauses.append("trade_date >= ?")
        params.append(start_date)
    if end_date:
        where_clauses.append("trade_date <= ?")
        params.append(end_date)
    
    query = (
        f"SELECT ts_code, trade_date, open, high, low, close, vol, amount "
        f"FROM read_parquet(?) WHERE {' AND '.join(where_clauses)} ORDER BY trade_date"
    )
    with get_connection() as con:
        try:
            df = con.execute(query, params).fetchdf()
        except Exception as exc:
            print(f"Error loading data for {ts_code}: {exc}")
            return pd.DataFrame()

    if not df.empty:
        df["trade_date"] = pd.to_datetime(df["trade_date"], format="%Y%m%d")
        df = df.sort_values("trade_date").reset_index(drop=True)
    return df


def delete_stock_indicators(ts_code: str, start_date: str | None = None, end_date: str | None = None) -> None:
    """Delete historical indicator data for a stock.
    
    If start_date and end_date are provided, only delete data within that range.
    Otherwise, delete all data for the stock.
    """
    features_base = settings.data_dir / "features" / "indicators"
    stock_dir = features_base / f"ts_code={ts_code}"
    
    if not stock_dir.exists():
        return
    
    # If no date range specified, delete all data for this stock
    if not start_date and not end_date:
        shutil.rmtree(stock_dir)
        print(f"Deleted all existing indicators for {ts_code}")
        return
    
    # If date range specified, need to selectively delete
    # Load existing data, filter out the date range, and resave
    import pyarrow.parquet as pq
    
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
        return
    
    combined = pd.concat(all_data, ignore_index=True)
    original_count = len(combined)
    
    # Filter out data in the specified date range
    mask = pd.Series([True] * len(combined))
    if start_date:
        mask &= combined["trade_date"] < start_date
    if end_date:
        mask &= combined["trade_date"] > end_date
    
    remaining = combined[mask]
    deleted_count = original_count - len(remaining)
    
    if deleted_count > 0:
        # Delete all and resave remaining
        shutil.rmtree(stock_dir)
        if not remaining.empty:
            save_indicators(remaining)
        print(f"Deleted {deleted_count} rows of indicators for {ts_code} in date range")
    else:
        print(f"No existing indicators to delete for {ts_code} in date range")


def save_indicators(df: pd.DataFrame) -> int:
    """Save indicators DataFrame to parquet files, partitioned by ts_code and year."""
    if df.empty:
        return 0

    if "ts_code" not in df.columns or "trade_date" not in df.columns:
        raise ValueError("indicators data must include ts_code and trade_date")

    features_base = settings.data_dir / "features" / "indicators"
    features_base.mkdir(parents=True, exist_ok=True)

    # Convert trade_date to string and extract year
    data = df.copy()
    if pd.api.types.is_datetime64_any_dtype(data["trade_date"]):
        data["trade_date"] = data["trade_date"].dt.strftime("%Y%m%d")
    data["year"] = data["trade_date"].str[:4]

    # Group by ts_code and year, then save to parquet
    total_saved = 0
    for (ts_code, year), group in data.groupby(["ts_code", "year"], sort=False):
        partition_dir = features_base / f"ts_code={ts_code}" / f"year={year}"
        partition_dir.mkdir(parents=True, exist_ok=True)
        new_rows = group.drop(columns=["year"])
        part_path = partition_dir / f"part-{uuid.uuid4().hex}.parquet"
        new_rows.to_parquet(part_path, index=False, engine="pyarrow")
        total_saved += len(new_rows)

    return total_saved


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Calculate technical indicators for all stocks")
    parser.add_argument("--start-date", type=str, default=None, help="Start date: YYYYMMDD or YYYY-MM-DD")
    parser.add_argument("--end-date", type=str, default=None, help="End date: YYYYMMDD or YYYY-MM-DD (default: today)")
    return parser.parse_args()


def normalize_date(date_str: str | None) -> str | None:
    """Normalize date string to YYYYMMDD format."""
    if not date_str:
        return None
    # Remove hyphens if present
    return date_str.replace("-", "")


def main() -> None:
    """Main function to calculate indicators for all stocks."""
    args = parse_args()
    start_date = normalize_date(args.start_date)
    end_date = normalize_date(args.end_date)
    
    # Validate date range
    if start_date and end_date:
        if start_date > end_date:
            raise SystemExit(
                f"Error: start_date ({start_date}) cannot be after end_date ({end_date}). "
                f"Please check your date arguments."
            )
    
    # If no date range specified, calculate for all history
    if start_date or end_date:
        date_range_str = f" from {start_date or 'start'} to {end_date or 'end'}"
        print(f"Calculating indicators{date_range_str}")
    else:
        print("Calculating indicators for all historical data")
    
    total_start = time.perf_counter()
    stock_list = load_stock_list()
    if not stock_list:
        raise SystemExit("No stock_basic data available")

    calculator = IndicatorCalculator()

    for idx, ts_code in enumerate(stock_list, start=1):
        stock_start = time.perf_counter()
        try:
            # Delete existing indicators for this stock (in date range if specified)
            delete_stock_indicators(ts_code, start_date, end_date)

            # Load daily data (filtered by date range if specified)
            daily_df = load_daily_data(ts_code, start_date, end_date)
            if daily_df.empty:
                print(f"[{idx}/{len(stock_list)}] {ts_code} skipped (no data)")
                continue

            # Calculate indicators
            indicators_df = calculator.calculate_all(daily_df)

            # Save to parquet
            saved_count = save_indicators(indicators_df)

            stock_elapsed = time.perf_counter() - stock_start
            print(
                f"[{idx}/{len(stock_list)}] {ts_code} "
                f"calculated {len(indicators_df)} rows, saved {saved_count} rows "
                f"elapsed={stock_elapsed:.2f}s"
            )
        except Exception as exc:
            stock_elapsed = time.perf_counter() - stock_start
            print(f"[{idx}/{len(stock_list)}] {ts_code} failed: {exc} elapsed={stock_elapsed:.2f}s")

    total_elapsed = time.perf_counter() - total_start
    print(f"\nTotal: processed {len(stock_list)} stocks, elapsed={total_elapsed:.2f}s ({total_elapsed/60:.2f} minutes)")


if __name__ == "__main__":
    main()
