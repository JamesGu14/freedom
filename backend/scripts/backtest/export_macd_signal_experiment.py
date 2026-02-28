#!/usr/bin/env python3
from __future__ import annotations

import argparse
import logging
import math
import sys
from pathlib import Path
from typing import Any

import pandas as pd

SCRIPT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(SCRIPT_ROOT))

from app.data.duckdb_backtest_store import list_open_trade_dates, list_stock_universe, normalize_date  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.data.duckdb_store import get_connection  # noqa: E402

logger = logging.getLogger(__name__)
MAX_HORIZON = 10


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export MACD golden-cross signal effectiveness to Excel.")
    parser.add_argument("--start-date", type=str, default="20150101", help="Signal start date (YYYYMMDD or YYYY-MM-DD)")
    parser.add_argument("--end-date", type=str, default="20251231", help="Signal end date (YYYYMMDD or YYYY-MM-DD)")
    parser.add_argument(
        "--output-path",
        type=str,
        default="logs/backtest/macd_signal_experiment_2015_2025.xlsx",
        help="Output excel path",
    )
    parser.add_argument(
        "--only-below-zero",
        action="store_true",
        help="Only keep events where macd<0 and macd_signal<0 on signal day",
    )
    parser.add_argument(
        "--split-events-by-year",
        action="store_true",
        default=True,
        help="Split event detail sheets by year (recommended)",
    )
    return parser.parse_args()


def _to_float(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(number):
        return default
    return number


def _build_trade_date_mapping(*, start_date: str, end_date: str, horizon: int) -> tuple[list[str], dict[str, dict[int, str]]]:
    all_dates = list_open_trade_dates(start_date=start_date, end_date=end_date)
    idx_map = {d: i for i, d in enumerate(all_dates)}
    next_map: dict[str, dict[int, str]] = {}
    for d in all_dates:
        pos = idx_map[d]
        next_map[d] = {}
        for h in range(1, horizon + 1):
            t = pos + h
            if t < len(all_dates):
                next_map[d][h] = all_dates[t]
    return all_dates, next_map


def _load_macd_events(*, start_date: str, end_date: str) -> pd.DataFrame:
    query = """
        WITH indicators AS (
            SELECT
                ts_code,
                trade_date,
                macd,
                macd_signal,
                macd_hist,
                LAG(macd_hist) OVER (PARTITION BY ts_code ORDER BY trade_date) AS prev_macd_hist
            FROM read_parquet(?, hive_partitioning=1, union_by_name=true)
            WHERE trade_date BETWEEN ? AND ?
        )
        SELECT
            ts_code,
            trade_date,
            macd,
            macd_signal,
            macd_hist,
            prev_macd_hist
        FROM indicators
        WHERE macd_hist > 0
          AND COALESCE(prev_macd_hist, 0) <= 0
    """
    with get_connection(read_only=True) as con:
        df = con.execute(
            query,
            [
                str(settings.data_dir / "features" / "indicators" / "ts_code=*" / "year=*" / "part-*.parquet"),
                start_date,
                end_date,
            ],
        ).fetchdf()
    if df.empty:
        return df
    df["trade_date"] = df["trade_date"].astype(str)
    df["ts_code"] = df["ts_code"].astype(str)
    return df


def _load_price_panel(*, start_date: str, end_date: str) -> pd.DataFrame:
    query = """
        WITH daily AS (
            SELECT ts_code, trade_date, open, close
            FROM read_parquet(?, hive_partitioning=1, union_by_name=true)
            WHERE trade_date BETWEEN ? AND ?
        ),
        limitp AS (
            SELECT ts_code, trade_date, up_limit
            FROM read_parquet(?, hive_partitioning=1, union_by_name=true)
            WHERE trade_date BETWEEN ? AND ?
        )
        SELECT
            d.ts_code,
            d.trade_date,
            d.open,
            d.close,
            l.up_limit
        FROM daily d
        LEFT JOIN limitp l
          ON d.ts_code = l.ts_code
         AND d.trade_date = l.trade_date
    """
    with get_connection(read_only=True) as con:
        df = con.execute(
            query,
            [
                str(settings.data_dir / "raw" / "daily" / "ts_code=*" / "year=*" / "part-*.parquet"),
                start_date,
                end_date,
                str(settings.data_dir / "raw" / "daily_limit" / "ts_code=*" / "year=*" / "part-*.parquet"),
                start_date,
                end_date,
            ],
        ).fetchdf()
    if df.empty:
        return df
    df["trade_date"] = df["trade_date"].astype(str)
    df["ts_code"] = df["ts_code"].astype(str)
    return df


def _build_events_dataframe(
    *,
    events_df: pd.DataFrame,
    price_df: pd.DataFrame,
    date_map: dict[str, dict[int, str]],
    horizon: int,
    only_below_zero: bool,
) -> pd.DataFrame:
    if events_df.empty:
        return pd.DataFrame()

    data = events_df.copy()
    data["cross_type"] = "standard"
    data.loc[(data["macd"].fillna(0) < 0) & (data["macd_signal"].fillna(0) < 0), "cross_type"] = "below_zero"
    if only_below_zero:
        data = data[data["cross_type"] == "below_zero"].copy()
    if data.empty:
        return data

    for h in range(1, horizon + 1):
        data[f"date_t{h}"] = data["trade_date"].map(lambda d: date_map.get(str(d), {}).get(h))

    panel = price_df[["ts_code", "trade_date", "open", "close", "up_limit"]].copy()
    panel["trade_date"] = panel["trade_date"].astype(str)

    t1_panel = panel.rename(
        columns={
            "trade_date": "date_t1",
            "open": "buy_open_t1",
            "close": "close_t1",
            "up_limit": "up_limit_t1",
        }
    )[["ts_code", "date_t1", "buy_open_t1", "close_t1", "up_limit_t1"]]
    data = data.merge(t1_panel, on=["ts_code", "date_t1"], how="left")

    for h in range(2, horizon + 1):
        close_panel = panel.rename(columns={"trade_date": f"date_t{h}", "close": f"close_t{h}"})[
            ["ts_code", f"date_t{h}", f"close_t{h}"]
        ]
        data = data.merge(close_panel, on=["ts_code", f"date_t{h}"], how="left")

    buy_open = pd.to_numeric(data["buy_open_t1"], errors="coerce")
    up_limit = pd.to_numeric(data["up_limit_t1"], errors="coerce")
    # Invalid when T+1 cannot be traded at open (open already at limit-up).
    can_trade = buy_open.notna() & ((up_limit.isna()) | (buy_open < up_limit - 1e-8))
    data = data[can_trade].copy()
    if data.empty:
        return data

    data["event_id"] = data["ts_code"].astype(str) + "_" + data["trade_date"].astype(str)
    data["buy_price"] = pd.to_numeric(data["buy_open_t1"], errors="coerce")

    close_cols = [f"close_t{h}" for h in range(1, horizon + 1)]
    for col in close_cols:
        data[col] = pd.to_numeric(data[col], errors="coerce")

    data["daily_ret_t1"] = data["close_t1"] / data["buy_price"] - 1.0
    for h in range(2, horizon + 1):
        data[f"daily_ret_t{h}"] = data[f"close_t{h}"] / data[f"close_t{h-1}"] - 1.0
    for h in range(1, horizon + 1):
        data[f"cum_ret_t{h}"] = data[f"close_t{h}"] / data["buy_price"] - 1.0

    data["valid_horizon"] = data[[f"close_t{h}" for h in range(1, horizon + 1)]].notna().sum(axis=1).astype(int)
    data["is_suspended_window"] = data["valid_horizon"] < horizon
    data["event_year"] = data["trade_date"].str[:4]
    return data


def _build_stats_by_horizon(events_df: pd.DataFrame, horizon: int) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for h in range(1, horizon + 1):
        dcol = f"daily_ret_t{h}"
        ccol = f"cum_ret_t{h}"
        d = pd.to_numeric(events_df.get(dcol), errors="coerce")
        c = pd.to_numeric(events_df.get(ccol), errors="coerce")
        d_valid = d.dropna()
        c_valid = c.dropna()
        rows.append(
            {
                "horizon": h,
                "sample_n": int(len(c_valid)),
                "win_rate_daily": _to_float((d_valid > 0).mean()) if len(d_valid) else 0.0,
                "avg_daily_ret": _to_float(d_valid.mean()) if len(d_valid) else 0.0,
                "median_daily_ret": _to_float(d_valid.median()) if len(d_valid) else 0.0,
                "p25_daily_ret": _to_float(d_valid.quantile(0.25)) if len(d_valid) else 0.0,
                "p75_daily_ret": _to_float(d_valid.quantile(0.75)) if len(d_valid) else 0.0,
                "win_rate_cum": _to_float((c_valid > 0).mean()) if len(c_valid) else 0.0,
                "avg_cum_ret": _to_float(c_valid.mean()) if len(c_valid) else 0.0,
                "median_cum_ret": _to_float(c_valid.median()) if len(c_valid) else 0.0,
                "p25_cum_ret": _to_float(c_valid.quantile(0.25)) if len(c_valid) else 0.0,
                "p75_cum_ret": _to_float(c_valid.quantile(0.75)) if len(c_valid) else 0.0,
                "max_cum_ret": _to_float(c_valid.max()) if len(c_valid) else 0.0,
                "min_cum_ret": _to_float(c_valid.min()) if len(c_valid) else 0.0,
            }
        )
    return pd.DataFrame(rows)


def _build_stats_yearly(events_df: pd.DataFrame, horizon: int) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    years = sorted(events_df["event_year"].dropna().astype(str).unique().tolist())
    for year in years:
        part = events_df[events_df["event_year"] == year]
        for h in range(1, horizon + 1):
            dcol = f"daily_ret_t{h}"
            ccol = f"cum_ret_t{h}"
            d = pd.to_numeric(part.get(dcol), errors="coerce").dropna()
            c = pd.to_numeric(part.get(ccol), errors="coerce").dropna()
            rows.append(
                {
                    "year": year,
                    "horizon": h,
                    "sample_n": int(len(c)),
                    "win_rate_cum": _to_float((c > 0).mean()) if len(c) else 0.0,
                    "avg_cum_ret": _to_float(c.mean()) if len(c) else 0.0,
                    "median_cum_ret": _to_float(c.median()) if len(c) else 0.0,
                    "win_rate_daily": _to_float((d > 0).mean()) if len(d) else 0.0,
                    "avg_daily_ret": _to_float(d.mean()) if len(d) else 0.0,
                }
            )
    return pd.DataFrame(rows)


def _build_readme_sheet(*, start_date: str, end_date: str, only_below_zero: bool) -> pd.DataFrame:
    cross_def = "macd_hist(t)>0 且 macd_hist(t-1)<=0"
    if only_below_zero:
        cross_def += " 且 macd(t)<0 且 macd_signal(t)<0"
    rows = [
        {"item": "样本区间", "value": f"{start_date} ~ {end_date}"},
        {"item": "金叉定义", "value": cross_def},
        {"item": "买入价", "value": "T+1 开盘价 open(T+1)"},
        {"item": "无效事件", "value": "T+1 开盘即涨停（open(T+1) >= up_limit(T+1)）"},
        {"item": "逐日收益定义", "value": "daily_ret_t1=close(T+1)/open(T+1)-1; daily_ret_th=close(T+h)/close(T+h-1)-1 (h>=2)"},
        {"item": "累计收益定义", "value": "cum_ret_th=close(T+h)/open(T+1)-1"},
        {"item": "缺失处理", "value": "未来不足 h 个交易日或缺价则该 horizon 留空"},
    ]
    return pd.DataFrame(rows)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    args = parse_args()

    start_date = normalize_date(args.start_date)
    end_date = normalize_date(args.end_date)
    output_path = Path(args.output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    all_dates, future_date_map = _build_trade_date_mapping(start_date="20100101", end_date="20991231", horizon=MAX_HORIZON)
    if not all_dates:
        raise ValueError("trade_calendar is empty")

    events_raw = _load_macd_events(start_date=start_date, end_date=end_date)
    if events_raw.empty:
        raise ValueError("no MACD golden-cross events found in selected range")

    all_date_set = set(all_dates)
    events_raw = events_raw[events_raw["trade_date"].isin(all_date_set)].copy()
    if events_raw.empty:
        raise ValueError("no valid events on open trading days")

    need_start = events_raw["trade_date"].min()
    need_end = end_date
    # Extend panel end to cover up to T+10 close for events near range end.
    for d in sorted(events_raw["trade_date"].unique().tolist(), reverse=True):
        dates = future_date_map.get(str(d), {})
        if dates:
            need_end = max(need_end, max(dates.values()))
            break

    logger.info("loading price panel: %s ~ %s", need_start, need_end)
    price_panel = _load_price_panel(start_date=need_start, end_date=need_end)
    if price_panel.empty:
        raise ValueError("price panel is empty")

    logger.info("building events dataframe...")
    events = _build_events_dataframe(
        events_df=events_raw,
        price_df=price_panel,
        date_map=future_date_map,
        horizon=MAX_HORIZON,
        only_below_zero=bool(args.only_below_zero),
    )
    if events.empty:
        raise ValueError("no tradable events after T+1 open-limit filter")

    universe = list_stock_universe()[["ts_code", "name", "industry"]].rename(columns={"name": "stock_name"})
    events = events.merge(universe, on="ts_code", how="left")

    ordered_cols = (
        ["event_id", "ts_code", "stock_name", "industry", "trade_date", "event_year", "cross_type"]
        + ["buy_price", "buy_open_t1", "up_limit_t1", "macd", "macd_signal", "macd_hist", "prev_macd_hist"]
        + [f"date_t{h}" for h in range(1, MAX_HORIZON + 1)]
        + [f"close_t{h}" for h in range(1, MAX_HORIZON + 1)]
        + [f"daily_ret_t{h}" for h in range(1, MAX_HORIZON + 1)]
        + [f"cum_ret_t{h}" for h in range(1, MAX_HORIZON + 1)]
        + ["valid_horizon", "is_suspended_window"]
    )
    events = events[[c for c in ordered_cols if c in events.columns]].sort_values(["trade_date", "ts_code"])

    stats_h = _build_stats_by_horizon(events, MAX_HORIZON)
    stats_y = _build_stats_yearly(events, MAX_HORIZON)
    readme_df = _build_readme_sheet(start_date=start_date, end_date=end_date, only_below_zero=bool(args.only_below_zero))

    logger.info("writing excel: %s", output_path)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        readme_df.to_excel(writer, sheet_name="README_口径说明", index=False)
        stats_h.to_excel(writer, sheet_name="Stats_ByHorizon", index=False)
        stats_y.to_excel(writer, sheet_name="Stats_Yearly", index=False)

        if args.split_events_by_year:
            for year, part in events.groupby("event_year", sort=True):
                sheet = f"Events_{year}"
                part.to_excel(writer, sheet_name=sheet[:31], index=False)
        else:
            # Excel row limit safeguard.
            if len(events) > 1_000_000:
                raise ValueError("events rows exceed excel limit; use --split-events-by-year")
            events.to_excel(writer, sheet_name="Events_事件明细", index=False)

    logger.info("done: events=%s, output=%s", len(events), output_path)


if __name__ == "__main__":
    main()
