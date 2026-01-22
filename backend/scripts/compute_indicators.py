#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

SCRIPT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_ROOT))

from app.data.duckdb_store import get_daily_with_adj, replace_features_daily  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compute indicators and store in DuckDB.")
    parser.add_argument("--ts-code", type=str, default="", help="Compute for a single ts_code")
    return parser.parse_args()


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    df = df.copy()
    df["adj_factor"] = df["adj_factor"].fillna(1.0)
    df["adj_close"] = df["close"] * df["adj_factor"]

    for window in [5, 10, 20, 30, 60, 120, 250]:
        df[f"ma_{window}"] = df["adj_close"].rolling(window=window).mean()

    # MACD (12,26,9)
    ema12 = df["adj_close"].ewm(span=12, adjust=False).mean()
    ema26 = df["adj_close"].ewm(span=26, adjust=False).mean()
    df["macd_dif"] = ema12 - ema26
    df["macd_dea"] = df["macd_dif"].ewm(span=9, adjust=False).mean()
    df["macd_hist"] = (df["macd_dif"] - df["macd_dea"]) * 2

    # RSI (14)
    delta = df["adj_close"].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.rolling(window=14).mean()
    avg_loss = loss.rolling(window=14).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    df["rsi_14"] = 100 - (100 / (1 + rs))

    # BOLL (20,2)
    df["boll_mid"] = df["adj_close"].rolling(window=20).mean()
    boll_std = df["adj_close"].rolling(window=20).std()
    df["boll_upper"] = df["boll_mid"] + 2 * boll_std
    df["boll_lower"] = df["boll_mid"] - 2 * boll_std

    # KDJ (9,3,3)
    low_n = df["low"].rolling(window=9).min()
    high_n = df["high"].rolling(window=9).max()
    rsv = (df["adj_close"] - low_n) / (high_n - low_n).replace(0, pd.NA) * 100
    df["kdj_k"] = rsv.ewm(com=2, adjust=False).mean()
    df["kdj_d"] = df["kdj_k"].ewm(com=2, adjust=False).mean()
    df["kdj_j"] = 3 * df["kdj_k"] - 2 * df["kdj_d"]

    return df[
        [
            "ts_code",
            "trade_date",
            "adj_close",
            "ma_5",
            "ma_10",
            "ma_20",
            "ma_30",
            "ma_60",
            "ma_120",
            "ma_250",
            "macd_dif",
            "macd_dea",
            "macd_hist",
            "rsi_14",
            "boll_mid",
            "boll_upper",
            "boll_lower",
            "kdj_k",
            "kdj_d",
            "kdj_j",
        ]
    ]


def load_ts_codes() -> list[str]:
    from app.data.duckdb_store import get_connection  # noqa: E402

    with get_connection() as con:
        rows = con.execute("SELECT DISTINCT ts_code FROM daily ORDER BY ts_code").fetchall()
    return [row[0] for row in rows]


def main() -> None:
    args = parse_args()
    ts_codes = [args.ts_code] if args.ts_code else load_ts_codes()
    if not ts_codes:
        raise SystemExit("No ts_code found in daily table")

    for idx, ts_code in enumerate(ts_codes, start=1):
        df = get_daily_with_adj(ts_code)
        features = compute_indicators(df)
        rows = replace_features_daily(ts_code, features)
        print(f"[{idx}/{len(ts_codes)}] {ts_code} features rows: {rows}")


if __name__ == "__main__":
    main()
