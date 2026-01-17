from __future__ import annotations

import sys
from abc import ABC, abstractmethod
from pathlib import Path

import pandas as pd

SCRIPT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(SCRIPT_ROOT))

from app.data.duckdb_store import (  # noqa: E402
    get_connection,
    list_daily,
    list_daily_basic,
    list_indicators,
)


class BaseStrategy(ABC):
    def __init__(
        self,
        stock_code: str,
        df: pd.DataFrame | None = None,
        include_daily_basic: bool = False,
    ):
        self.stock_code = stock_code
        if df is None:
            df = self._load_stock_df_from_duckdb(stock_code, include_daily_basic=include_daily_basic)
        self.df = df if df is not None else None

    @abstractmethod
    def predict_date(self, select_date) -> str:
        raise NotImplementedError

    def _resolve_ts_code(self, stock_code: str) -> str:
        if "." in stock_code:
            return stock_code
        with get_connection() as con:
            row = con.execute(
                "SELECT ts_code FROM stock_basic WHERE symbol = ? LIMIT 1",
                [stock_code],
            ).fetchone()
        if not row:
            return stock_code
        return row[0]

    def _load_stock_df_from_duckdb(self, stock_code: str, include_daily_basic: bool) -> pd.DataFrame | None:
        ts_code = self._resolve_ts_code(stock_code)
        daily_rows = list_daily(ts_code)
        indicator_rows = list_indicators(ts_code)
        if not daily_rows:
            return None
        if not indicator_rows:
            return None

        daily_df = pd.DataFrame(daily_rows)
        indicators_df = pd.DataFrame(indicator_rows)

        if include_daily_basic:
            daily_basic_rows = list_daily_basic(ts_code)
            if not daily_basic_rows:
                return None
            daily_basic_df = pd.DataFrame(daily_basic_rows)
            if "close" in daily_basic_df.columns:
                daily_basic_df = daily_basic_df.rename(columns={"close": "close_basic"})
            df = daily_df.merge(daily_basic_df, on=["ts_code", "trade_date"], how="left")
            df = df.merge(indicators_df, on=["ts_code", "trade_date"], how="left")
        else:
            df = daily_df.merge(indicators_df, on=["ts_code", "trade_date"], how="left")

        df = df.rename(
            columns={
                "trade_date": "date",
                "vol": "volume",
                "macd": "macd_dif",
                "macd_signal": "macd_dea",
            }
        )
        return df
