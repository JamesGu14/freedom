import sys
from pathlib import Path

import pandas as pd
import numpy as np

SCRIPT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(SCRIPT_ROOT))

from scripts.strategy.base_strategy import BaseStrategy  # noqa: E402

REQUIRED_COLUMNS = {
    "date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "macd_dif",
    "macd_dea",
    "rsi",
}


class EarlyBreakoutSignalModel(BaseStrategy):
    def __init__(
        self,
        stock_code: str,
        df: pd.DataFrame | None = None,
        params: dict | None = None,
        colmap: dict | None = None,
    ):
        super().__init__(stock_code, df=df, include_daily_basic=False)
        self.params = self._merge_params(params)
        if self.df is not None:
            self.df = self._prepare_df(self.df, colmap)
            self._precompute()

    def _merge_params(self, params: dict | None) -> dict:
        default_params = {
            "base_lookback": 30,
            "breakout_lookback": 20,
            "ma_fast": 5,
            "ma_mid": 10,
            "ma_slow": 20,
            "ma_trend": 60,
            "vol_ma": 5,
            "vol_ratio_th": 1.8,
            "body_ratio_th": 0.6,
            "rsi_regime": 50,
            "cooldown_days": 5,
            "extreme_move_pct": 0.09,
        }
        if params is not None:
            default_params.update(params)
        return default_params

    def _normalize_colmap(self, df: pd.DataFrame, colmap: dict | None) -> dict:
        if not colmap:
            return {}
        keys = set(colmap.keys())
        values = set(colmap.values())
        if keys.issubset(REQUIRED_COLUMNS):
            return {v: k for k, v in colmap.items()}
        if values.issubset(REQUIRED_COLUMNS):
            return colmap
        return colmap

    def _prepare_df(self, df: pd.DataFrame, colmap: dict | None) -> pd.DataFrame:
        if not isinstance(df, pd.DataFrame):
            raise TypeError("df must be a pandas DataFrame")
        df = df.copy()
        rename_map = self._normalize_colmap(df, colmap)
        if rename_map:
            df = df.rename(columns=rename_map)

        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date")
        else:
            if not isinstance(df.index, pd.DatetimeIndex):
                df.index = pd.to_datetime(df.index)

        df = df.sort_index()
        df = df[~df.index.duplicated(keep="last")]
        return df

    def _precompute(self) -> None:
        p = self.params
        df = self.df

        close = df["close"]
        high = df["high"]
        low = df["low"]
        open_ = df["open"]
        volume = df["volume"]
        dif = df["macd_dif"]
        dea = df["macd_dea"]
        rsi = df["rsi"]

        df["ma_fast"] = close.rolling(p["ma_fast"]).mean()
        df["ma_mid"] = close.rolling(p["ma_mid"]).mean()
        df["ma_slow"] = close.rolling(p["ma_slow"]).mean()
        df["ma_trend"] = close.rolling(p["ma_trend"]).mean()
        df["ma_slow_slope"] = df["ma_slow"] - df["ma_slow"].shift(1)

        base_n = p["base_lookback"]
        breakout_n = p["breakout_lookback"]

        range_ratio = (high.rolling(base_n).max() - low.rolling(base_n).min()) / close
        cond_range = range_ratio <= 0.35

        cond_ma_sticky = (
            (df["ma_fast"] - df["ma_mid"]).abs() / close < 0.03
        ) & ((df["ma_mid"] - df["ma_slow"]).abs() / close < 0.05)

        cond_no_big_run = close / low.rolling(base_n).min() <= 1.6

        df["platform_cnt"] = (
            cond_range.astype(int) + cond_ma_sticky.astype(int) + cond_no_big_run.astype(int)
        )

        df["hh"] = high.rolling(breakout_n).max().shift(1)
        first_break = close.shift(1) <= df["hh"].shift(1)

        body = close - open_
        span = (high - low).replace(0, np.nan)
        body_ratio = body / span
        bullish_body = (close > open_) & (body_ratio >= p["body_ratio_th"])

        df["vol_ma"] = volume.rolling(p["vol_ma"]).mean()
        vol_expand = volume >= p["vol_ratio_th"] * df["vol_ma"]

        breakout_valid = (close > df["hh"]) & first_break & bullish_body & vol_expand
        df["breakout_price"] = np.where(breakout_valid, df["hh"], np.nan)

        macd_cross_up = (dif > dea) & (dif.shift(1) <= dea.shift(1)) & ((dif - dea) > 0)
        rsi_up = (rsi > p["rsi_regime"]) & (rsi.shift(1) <= p["rsi_regime"])
        ma_bull = (
            (df["ma_fast"] > df["ma_mid"])
            & (df["ma_mid"] > df["ma_slow"])
            & (df["ma_slow_slope"] > 0)
        )
        df["momentum_cnt"] = macd_cross_up.astype(int) + rsi_up.astype(int) + ma_bull.astype(int)

        base_buy = (df["platform_cnt"] >= 2) & breakout_valid & (df["momentum_cnt"] >= 1)

        macd_cross_down = (dif < dea) & (dif.shift(1) >= dea.shift(1)) & (dif > 0) & (dea > 0)
        sell_ma = (close < df["ma_slow"]) & (df["ma_slow_slope"] < 0)
        vol_ma5 = volume.rolling(5).mean()
        sell_break = (close < open_) & (volume > 1.5 * vol_ma5) & (close < low.shift(1))
        base_sell = sell_ma | macd_cross_down | sell_break

        df["base_buy"] = base_buy
        df["base_sell"] = base_sell

        df["extreme_move"] = close.pct_change().abs() >= p["extreme_move_pct"]

        invalid_mask = df[["open", "high", "low", "close", "volume", "macd_dif", "macd_dea", "rsi"]].isna().any(axis=1)
        df["invalid"] = invalid_mask

        signal_final = []
        cooldown_days = int(p["cooldown_days"])
        active_breakout_price = None
        days_since_buy = 0

        for idx, row in df.iterrows():
            if active_breakout_price is not None:
                days_since_buy += 1

            if row["invalid"] or row["extreme_move"]:
                signal = "HOLD"
            else:
                sell_fail = False
                if active_breakout_price is not None and days_since_buy <= 10:
                    if row["close"] < active_breakout_price:
                        sell_fail = True

                if sell_fail:
                    signal_candidate = "SELL"
                elif row["base_buy"]:
                    signal_candidate = "BUY"
                elif row["base_sell"]:
                    signal_candidate = "SELL"
                else:
                    signal_candidate = "HOLD"

                if signal_candidate in ("BUY", "SELL"):
                    start = max(0, len(signal_final) - cooldown_days)
                    recent = signal_final[start:]
                    if signal_candidate in recent:
                        signal = "HOLD"
                    else:
                        signal = signal_candidate
                else:
                    signal = "HOLD"

            if signal == "BUY":
                active_breakout_price = row["breakout_price"]
                days_since_buy = 0
            elif signal == "SELL":
                active_breakout_price = None
                days_since_buy = 0

            signal_final.append(signal)

        df["signal"] = pd.Series(signal_final, index=df.index)
        self.df = df

    def predict_date(self, select_date) -> str:
        date = pd.Timestamp(select_date)
        if date not in self.df.index:
            raise KeyError(f"{self.stock_code}: date not found {date}")
        row = self.df.loc[date]
        if row[["open", "high", "low", "close", "volume", "macd_dif", "macd_dea", "rsi"]].isna().any():
            return "HOLD"
        signal = row.get("signal")
        if pd.isna(signal):
            return "HOLD"
        return str(signal)


def _make_df(date, open_, high, low, close, volume, macd_dif, macd_dea, rsi):
    return pd.DataFrame(
        {
            "date": date,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "macd_dif": macd_dif,
            "macd_dea": macd_dea,
            "rsi": rsi,
        }
    )


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python second.py <stock_code> <date>")
        raise SystemExit(1)

    stock_code = sys.argv[1]
    select_date = sys.argv[2]

    model = EarlyBreakoutSignalModel(stock_code, df=None)
    print(model.predict_date(select_date))


def test_breakout_buy():
    df = _make_df(
        [
            "2025-01-01",
            "2025-01-02",
            "2025-01-03",
            "2025-01-04",
            "2025-01-05",
            "2025-01-06",
            "2025-01-07",
            "2025-01-08",
        ],
        [10, 10.05, 10.0, 10.02, 10.01, 10.02, 10.1, 10.5],
        [10.2, 10.2, 10.15, 10.2, 10.2, 10.2, 10.3, 11.6],
        [9.9, 9.95, 9.9, 9.95, 9.95, 9.95, 10.0, 10.4],
        [10.0, 10.0, 10.05, 10.03, 10.02, 10.05, 10.2, 11.5],
        [100, 100, 100, 100, 100, 100, 100, 900],
        [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.1],
        [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.05],
        [45, 46, 47, 48, 49, 49, 49, 55],
    )
    model = EarlyBreakoutSignalModel(
        "T1",
        df,
        params={
            "base_lookback": 5,
            "breakout_lookback": 3,
            "ma_fast": 2,
            "ma_mid": 3,
            "ma_slow": 4,
            "ma_trend": 5,
            "vol_ma": 2,
            "cooldown_days": 2,
        },
    )
    assert model.predict_date("2025-01-08") == "BUY"


def test_cooldown_blocks_second_buy():
    df = _make_df(
        [
            "2025-01-01",
            "2025-01-02",
            "2025-01-03",
            "2025-01-04",
            "2025-01-05",
            "2025-01-06",
            "2025-01-07",
            "2025-01-08",
            "2025-01-09",
        ],
        [10, 10.05, 10.0, 10.02, 10.01, 10.02, 10.1, 10.5, 10.6],
        [10.2, 10.2, 10.15, 10.2, 10.2, 10.2, 10.3, 11.6, 11.8],
        [9.9, 9.95, 9.9, 9.95, 9.95, 9.95, 10.0, 10.4, 10.5],
        [10.0, 10.0, 10.05, 10.03, 10.02, 10.05, 10.2, 11.5, 11.7],
        [100, 100, 100, 100, 100, 100, 100, 900, 900],
        [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.1, 0.1],
        [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.05, 0.05],
        [45, 46, 47, 48, 49, 49, 49, 55, 55],
    )
    model = EarlyBreakoutSignalModel(
        "T2",
        df,
        params={
            "base_lookback": 5,
            "breakout_lookback": 3,
            "ma_fast": 2,
            "ma_mid": 3,
            "ma_slow": 4,
            "ma_trend": 5,
            "vol_ma": 2,
            "cooldown_days": 5,
        },
    )
    assert model.predict_date("2025-01-08") == "BUY"
    assert model.predict_date("2025-01-09") == "HOLD"


def test_breakout_fail_sell():
    df = _make_df(
        [
            "2025-01-01",
            "2025-01-02",
            "2025-01-03",
            "2025-01-04",
            "2025-01-05",
            "2025-01-06",
            "2025-01-07",
            "2025-01-08",
            "2025-01-09",
        ],
        [10, 10.05, 10.0, 10.02, 10.01, 10.02, 10.1, 10.5, 10.4],
        [10.2, 10.2, 10.15, 10.2, 10.2, 10.2, 10.3, 11.6, 10.6],
        [9.9, 9.95, 9.9, 9.95, 9.95, 9.95, 10.0, 10.4, 9.8],
        [10.0, 10.0, 10.05, 10.03, 10.02, 10.05, 10.2, 11.5, 9.9],
        [100, 100, 100, 100, 100, 100, 100, 900, 150],
        [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.1, 0.1],
        [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.05, 0.05],
        [45, 46, 47, 48, 49, 49, 49, 55, 40],
    )
    model = EarlyBreakoutSignalModel(
        "T3",
        df,
        params={
            "base_lookback": 5,
            "breakout_lookback": 3,
            "ma_fast": 2,
            "ma_mid": 3,
            "ma_slow": 4,
            "ma_trend": 5,
            "vol_ma": 2,
            "cooldown_days": 2,
        },
    )
    assert model.predict_date("2025-01-08") == "BUY"
    assert model.predict_date("2025-01-09") == "SELL"


def test_extreme_move_hold():
    df = _make_df(
        ["2025-01-01", "2025-01-02", "2025-01-03"],
        [10, 10.0, 10.0],
        [10.1, 10.1, 12.0],
        [9.9, 9.9, 9.9],
        [10.0, 10.0, 12.0],
        [100, 100, 900],
        [0.0, 0.0, 0.1],
        [0.0, 0.0, 0.05],
        [45, 46, 55],
    )
    model = EarlyBreakoutSignalModel(
        "T4",
        df,
        params={
            "base_lookback": 2,
            "breakout_lookback": 2,
            "ma_fast": 2,
            "ma_mid": 2,
            "ma_slow": 2,
            "ma_trend": 2,
            "vol_ma": 2,
            "extreme_move_pct": 0.09,
        },
    )
    assert model.predict_date("2025-01-03") == "HOLD"
