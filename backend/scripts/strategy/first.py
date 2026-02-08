#!/usr/bin/env python3
from __future__ import annotations

import logging
import sys
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(SCRIPT_ROOT))

import pandas as pd

from app.data.duckdb_store import list_indicators  # noqa: E402
from app.data.mongo_stock import list_stock_codes  # noqa: E402
from scripts.strategy.base_strategy import BaseStrategy  # noqa: E402

logger = logging.getLogger(__name__)


def load_all_stocks() -> list[str]:
    """Load all stock codes from MongoDB."""
    try:
        return list_stock_codes()
    except Exception as exc:
        raise SystemExit(f"Failed to load stock_basic from MongoDB: {exc}") from exc


class MaCrossSignalModel(BaseStrategy):
    def __init__(self, stock_code: str):
        super().__init__(stock_code, include_daily_basic=False)
        if self.df is None:
            return
        df = self.df.copy()
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date")
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)
        self.df = df.sort_index()

    def predict_date(self, select_date) -> str:
        if self.df is None or self.df.empty:
            return "HOLD"
        date = pd.Timestamp(select_date)
        if date not in self.df.index:
            raise KeyError(f"{self.stock_code}: date not found {date}")
        idx = self.df.index.get_loc(date)
        if isinstance(idx, slice) or idx == 0:
            return "HOLD"
        yesterday = self.df.iloc[idx - 1]
        today = self.df.iloc[idx]

        ma5_yesterday = yesterday.get("ma5")
        ma20_yesterday = yesterday.get("ma20")
        ma5_today = today.get("ma5")
        ma20_today = today.get("ma20")

        if any(x is None for x in [ma5_yesterday, ma20_yesterday, ma5_today, ma20_today]):
            return "HOLD"
        if ma5_yesterday < ma20_yesterday and ma5_today > ma20_today:
            return "BUY"
        return "HOLD"


def check_ma5_cross_above_ma20(ts_code: str) -> bool:
    """
    Check if ma5 crosses above ma20 in the past 2 days.
    Returns True if ma5 was below ma20 yesterday and above ma20 today.
    """
    indicators = list_indicators(ts_code)

    # Need at least 2 days of data
    if len(indicators) < 2:
        return False

    # Get last 2 days (most recent first if sorted descending, or last 2 if ascending)
    # list_indicators returns data ordered by trade_date ascending, so last 2 are most recent
    last_two = indicators[-2:]

    # Check if we have ma5 and ma20 columns
    if "ma5" not in last_two[0] or "ma20" not in last_two[0]:
        return False

    # Yesterday (second to last) and today (last)
    yesterday = last_two[0]
    today = last_two[1]

    # Check if ma5 crosses above ma20
    # Yesterday: ma5 < ma20
    # Today: ma5 > ma20
    ma5_yesterday = yesterday.get("ma5")
    ma20_yesterday = yesterday.get("ma20")
    ma5_today = today.get("ma5")
    ma20_today = today.get("ma20")

    # Check for None values
    if any(x is None for x in [ma5_yesterday, ma20_yesterday, ma5_today, ma20_today]):
        return False

    # Check if cross occurred
    if ma5_yesterday < ma20_yesterday and ma5_today > ma20_today:
        return True

    return False


def main() -> None:
    """Main function to check ma5 crossing above ma20 for all stocks."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    logger.info("Loading all stocks...")
    stock_list = load_all_stocks()
    logger.info("Found %s stocks", len(stock_list))

    crossed_stocks = []

    for idx, ts_code in enumerate(stock_list, start=1):
        try:
            if check_ma5_cross_above_ma20(ts_code):
                crossed_stocks.append(ts_code)
                logger.info("[%s/%s] %s: ma5 crossed above ma20", idx, len(stock_list), ts_code)
        except Exception:
            # Skip stocks with errors
            continue

    logger.info("Total stocks with ma5 crossing above ma20: %s", len(crossed_stocks))


if __name__ == "__main__":
    main()
