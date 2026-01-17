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
    "kdj_k",
    "kdj_d",
    "rsi",
}


class DailySignalModel(BaseStrategy):
    def __init__(
        self,
        stock_code: str,
        df: pd.DataFrame | None = None,
        params: dict | None = None,
        colmap: dict | None = None,
    ):
        super().__init__(stock_code, df=df, include_daily_basic=True)
        self.params = self._merge_params(params)
        self.df = self._prepare_df(self.df, colmap)
        self._precompute()

    def _merge_params(self, params: dict | None) -> dict:
        default_params = {
            "ma_window": 20,
            "vol_ma_window": 5,
            "cooldown_days": 3,
            "extreme_move_pct": 0.08,
            "require_min_positive": 2,
            "require_min_negative": 2,
            "buy_threshold": 2.0,
            "sell_threshold": -2.0,
            "range_extra_strict": True,
            "range_threshold_bump": 0.5,
        }
        if params:
            default_params.update(params)
        return default_params

    def _normalize_colmap(self, df: pd.DataFrame, colmap: dict | None) -> dict:
        if not colmap:
            return {}
        keys = set(colmap.keys())
        values = set(colmap.values())
        if keys.issubset(REQUIRED_COLUMNS):
            # colmap: standard -> actual
            return {v: k for k, v in colmap.items()}
        if values.issubset(REQUIRED_COLUMNS):
            # colmap: actual -> standard
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
        volume = df["volume"]

        df["ma"] = close.rolling(p["ma_window"]).mean()
        df["ma_slope"] = df["ma"] - df["ma"].shift(1)

        trend_up = (close > df["ma"]) & (df["ma_slope"] > 0)
        trend_down = (close < df["ma"]) & (df["ma_slope"] < 0)
        df["trend_state"] = np.where(trend_up, "UP", np.where(trend_down, "DOWN", "RANGE"))

        buy_th = p["buy_threshold"]
        sell_th = p["sell_threshold"]
        if p["range_extra_strict"]:
            df["buy_th"] = np.where(df["trend_state"] == "RANGE", buy_th + p["range_threshold_bump"], buy_th)
            df["sell_th"] = np.where(df["trend_state"] == "RANGE", sell_th - p["range_threshold_bump"], sell_th)
        else:
            df["buy_th"] = buy_th
            df["sell_th"] = sell_th

        dif = df["macd_dif"]
        dea = df["macd_dea"]
        macd_cross_up = (dif > dea) & (dif.shift(1) <= dea.shift(1))
        macd_cross_down = (dif < dea) & (dif.shift(1) >= dea.shift(1))

        score_macd = np.select(
            [
                macd_cross_up & (dif < 0) & (dea < 0),
                macd_cross_up & (dif > 0) & (dea > 0),
                macd_cross_down & (dif > 0) & (dea > 0),
                macd_cross_down & (dif < 0) & (dea < 0),
            ],
            [1.0, 0.5, -1.0, -0.5],
            default=0.0,
        )

        k = df["kdj_k"]
        d = df["kdj_d"]
        kdj_cross_up = (k > d) & (k.shift(1) <= d.shift(1))
        kdj_cross_down = (k < d) & (k.shift(1) >= d.shift(1))

        score_kdj = np.select(
            [
                kdj_cross_up & (k < 30),
                kdj_cross_up & (k >= 30) & (k < 50),
                kdj_cross_down & (k > 70),
                kdj_cross_down & (k > 50) & (k <= 70),
            ],
            [1.0, 0.5, -1.0, -0.5],
            default=0.0,
        )

        rsi = df["rsi"]
        rsi_upturn = (rsi > rsi.shift(1)) & (rsi.shift(1) <= rsi.shift(2))
        rsi_downturn = (rsi < rsi.shift(1)) & (rsi.shift(1) >= rsi.shift(2))

        score_rsi = np.select(
            [
                (rsi < 30) & rsi_upturn,
                (rsi >= 30) & (rsi < 50) & (rsi > rsi.shift(1)),
                (rsi > 70) & rsi_downturn,
                (rsi > 50) & (rsi <= 70) & (rsi < rsi.shift(1)),
            ],
            [1.0, 0.5, -1.0, -0.5],
            default=0.0,
        )

        df["vol_ma"] = volume.rolling(p["vol_ma_window"]).mean()
        up_day = close > close.shift(1)
        down_day = close < close.shift(1)
        vol_expand = volume > df["vol_ma"]

        score_vol = np.select(
            [up_day & vol_expand, down_day & vol_expand],
            [1.0, -1.0],
            default=0.0,
        )

        df["score_macd"] = pd.Series(score_macd, index=df.index).fillna(0.0)
        df["score_kdj"] = pd.Series(score_kdj, index=df.index).fillna(0.0)
        df["score_rsi"] = pd.Series(score_rsi, index=df.index).fillna(0.0)
        df["score_vol"] = pd.Series(score_vol, index=df.index).fillna(0.0)

        df["score_total"] = df[["score_macd", "score_kdj", "score_rsi", "score_vol"]].sum(axis=1)

        df["pos_cnt"] = (df[["score_macd", "score_kdj", "score_rsi", "score_vol"]] > 0).sum(axis=1)
        df["neg_cnt"] = (df[["score_macd", "score_kdj", "score_rsi", "score_vol"]] < 0).sum(axis=1)

        signal_raw = np.where(
            (df["pos_cnt"] >= 2) & (df["neg_cnt"] >= 2),
            "HOLD",
            np.where(
                (df["score_total"] >= df["buy_th"]) & (df["pos_cnt"] >= p["require_min_positive"]),
                "BUY",
                np.where(
                    (df["score_total"] <= df["sell_th"]) & (df["neg_cnt"] >= p["require_min_negative"]),
                    "SELL",
                    "HOLD",
                ),
            ),
        )
        df["signal_raw"] = signal_raw

        signal_filtered = np.where(
            (df["trend_state"] == "UP") & (df["signal_raw"] == "SELL"),
            "HOLD",
            np.where(
                (df["trend_state"] == "DOWN") & (df["signal_raw"] == "BUY"),
                "HOLD",
                df["signal_raw"],
            ),
        )

        ret = close.pct_change()
        signal_filtered = np.where(np.abs(ret) >= p["extreme_move_pct"], "HOLD", signal_filtered)

        signal_filtered = pd.Series(signal_filtered, index=df.index)

        signal_final = []
        cooldown_days = int(p["cooldown_days"])
        for i, sig in enumerate(signal_filtered.tolist()):
            if sig in ("BUY", "SELL"):
                start = max(0, i - cooldown_days)
                recent = signal_final[start:i]
                if sig in recent:
                    signal_final.append("HOLD")
                    continue
            signal_final.append(sig)

        df["signal"] = pd.Series(signal_final, index=df.index)

        invalid_mask = df["close"].isna()
        df.loc[invalid_mask, "signal"] = "HOLD"
        df.loc[invalid_mask, "signal_raw"] = "HOLD"

        self.df = df

    def predict_date(self, select_date) -> str:
        date = pd.Timestamp(select_date)
        if date not in self.df.index:
            raise KeyError(f"{self.stock_code}: date not found {date}")
        signal = self.df.loc[date, "signal"]
        if pd.isna(signal):
            return "HOLD"
        return str(signal)

    def get_features(self, select_date) -> dict:
        date = pd.Timestamp(select_date)
        if date not in self.df.index:
            raise KeyError(f"{self.stock_code}: date not found {date}")
        row = self.df.loc[date]
        return {
            "trend_state": row.get("trend_state"),
            "score_macd": row.get("score_macd"),
            "score_kdj": row.get("score_kdj"),
            "score_rsi": row.get("score_rsi"),
            "score_vol": row.get("score_vol"),
            "score_total": row.get("score_total"),
            "signal_raw": row.get("signal_raw"),
            "signal": row.get("signal"),
        }

    def available_dates(self) -> pd.DatetimeIndex:
        return self.df.index


def _make_df(date, open_, high, low, close, volume, macd_dif, macd_dea, kdj_k, kdj_d, rsi):
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
            "kdj_k": kdj_k,
            "kdj_d": kdj_d,
            "rsi": rsi,
        }
    )


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python third.py <stock_code> <date>")
        raise SystemExit(1)

    stock_code = sys.argv[1]
    select_date = sys.argv[2]

    model = DailySignalModel(stock_code)
    signal = model.predict_date(select_date)
    cn_map = {"BUY": "买入", "SELL": "卖出", "HOLD": "不操作"}
    print(cn_map.get(signal, "不操作"))


def test_trend_filter_up_blocks_sell():
    df = _make_df(
        ["2025-01-01", "2025-01-02", "2025-01-03", "2025-01-04"],
        [10, 11, 12, 12.5],
        [10.5, 11.5, 12.5, 13.5],
        [9.5, 10.5, 11.5, 12.0],
        [10, 11, 12, 13],
        [100, 100, 100, 90],
        [1.0, 1.0, 1.0, 0.5],
        [0.5, 0.5, 0.5, 0.6],
        [80, 80, 80, 60],
        [70, 70, 70, 65],
        [75, 75, 75, 65],
    )
    model = DailySignalModel("T1", df, params={"ma_window": 2, "vol_ma_window": 2})
    assert model.predict_date("2025-01-04") == "HOLD"


def test_trend_filter_down_blocks_buy():
    df = _make_df(
        ["2025-01-01", "2025-01-02", "2025-01-03", "2025-01-04"],
        [13, 12, 11, 10.5],
        [13.5, 12.5, 11.5, 11],
        [12.5, 11.5, 10.5, 10],
        [13, 12, 11, 10],
        [100, 100, 100, 90],
        [-0.6, -0.6, -0.6, -0.4],
        [-0.5, -0.5, -0.5, -0.5],
        [20, 20, 20, 25],
        [30, 30, 30, 24],
        [25, 25, 25, 28],
    )
    model = DailySignalModel("T2", df, params={"ma_window": 2, "vol_ma_window": 2})
    assert model.predict_date("2025-01-04") == "HOLD"


def test_cooldown_blocks_consecutive_buy():
    df = _make_df(
        ["2025-01-01", "2025-01-02", "2025-01-03", "2025-01-04"],
        [10, 10.5, 11, 11.5],
        [10.5, 11, 11.5, 12],
        [9.8, 10.2, 10.6, 11],
        [10, 10.8, 11.2, 11.6],
        [100, 120, 140, 160],
        [-0.1, -0.1, -0.1, -0.1],
        [-0.1, -0.1, -0.1, -0.1],
        [40, 40, 40, 40],
        [40, 40, 40, 40],
        [35, 36, 37, 38],
    )
    model = DailySignalModel(
        "T3",
        df,
        params={
            "ma_window": 2,
            "vol_ma_window": 2,
            "cooldown_days": 2,
            "range_extra_strict": False,
            "buy_threshold": 1.5,
        },
    )
    assert model.predict_date("2025-01-03") == "BUY"
    assert model.predict_date("2025-01-04") == "HOLD"


def test_extreme_move_forces_hold():
    df = _make_df(
        ["2025-01-01", "2025-01-02", "2025-01-03"],
        [10, 10.5, 12],
        [10.5, 11, 12.5],
        [9.8, 10.2, 11.5],
        [10, 10.4, 12.5],
        [100, 110, 120],
        [-0.6, -0.6, -0.4],
        [-0.5, -0.5, -0.5],
        [20, 20, 25],
        [30, 30, 24],
        [25, 25, 28],
    )
    model = DailySignalModel(
        "T4",
        df,
        params={"ma_window": 2, "vol_ma_window": 2, "extreme_move_pct": 0.05, "range_extra_strict": False},
    )
    assert model.predict_date("2025-01-03") == "HOLD"


def test_missing_date_raises_keyerror():
    df = _make_df(
        ["2025-01-01", "2025-01-02"],
        [10, 10.5],
        [10.5, 11],
        [9.8, 10.2],
        [10, 10.8],
        [100, 110],
        [-0.6, -0.6],
        [-0.5, -0.5],
        [20, 20],
        [30, 30],
        [25, 25],
    )
    model = DailySignalModel("T5", df, params={"ma_window": 2, "vol_ma_window": 2})
    try:
        model.predict_date("2025-01-03")
        assert False, "expected KeyError"
    except KeyError:
        assert True
