#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(SCRIPT_ROOT))

from app.data.duckdb_store import get_connection, list_indicators  # noqa: E402


def load_all_stocks() -> list[str]:
    """Load all stock codes from DuckDB."""
    with get_connection() as con:
        try:
            rows = con.execute("SELECT ts_code FROM stock_basic ORDER BY ts_code").fetchall()
        except Exception as exc:
            raise SystemExit(f"Failed to load stock_basic: {exc}") from exc
    return [row[0] for row in rows]


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
    print("Loading all stocks...")
    stock_list = load_all_stocks()
    print(f"Found {len(stock_list)} stocks\n")

    crossed_stocks = []

    for idx, ts_code in enumerate(stock_list, start=1):
        try:
            if check_ma5_cross_above_ma20(ts_code):
                crossed_stocks.append(ts_code)
                print(f"[{idx}/{len(stock_list)}] {ts_code}: ma5 crossed above ma20")
        except Exception:
            # Skip stocks with errors
            continue

    print(f"\nTotal stocks with ma5 crossing above ma20: {len(crossed_stocks)}")


if __name__ == "__main__":
    main()
