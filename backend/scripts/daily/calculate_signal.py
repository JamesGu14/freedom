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


def main() -> None:
    args = parse_args()
    given_date = getattr(args, "given_date", None) or "2026-01-16"
    trade_date = normalize_date(given_date)

    if not settings.tushare_token:
        raise SystemExit("TUSHARE_TOKEN is required")

    pro = ts.pro_api(settings.tushare_token)
    if not is_trading_day(pro, trade_date):
        raise SystemExit(f"{trade_date} is not a trading day")

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


if __name__ == "__main__":
    main()
