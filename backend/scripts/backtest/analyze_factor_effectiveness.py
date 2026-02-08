#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from tqdm import tqdm

SCRIPT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(SCRIPT_ROOT))

from app.data.duckdb_backtest_store import list_open_trade_dates, list_stock_universe, normalize_date  # noqa: E402
from app.quant.base import StrategyContext  # noqa: E402
from app.quant.context import load_daily_data_bundle  # noqa: E402
from app.quant.factors_sector import build_sector_strength_map  # noqa: E402
from app.quant.registry import load_strategy  # noqa: E402

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze factor effectiveness for a strategy.")
    parser.add_argument("--start-date", type=str, required=True, help="Start date YYYYMMDD or YYYY-MM-DD")
    parser.add_argument("--end-date", type=str, required=True, help="End date YYYYMMDD or YYYY-MM-DD")
    parser.add_argument("--strategy-key", type=str, default="multifactor_v1", help="Strategy key in registry")
    parser.add_argument(
        "--score-direction",
        type=str,
        default="normal",
        choices=["normal", "reverse"],
        help="Use normal score or reverse score for diagnostics (default: normal)",
    )
    parser.add_argument("--deciles", type=int, default=10, help="Number of score buckets (default: 10)")
    parser.add_argument("--top-k", type=int, default=100, help="Top-K for turnover diagnostics (default: 100)")
    parser.add_argument("--min-list-days", type=int, default=120, help="Minimum listing days filter (default: 120)")
    parser.add_argument(
        "--min-amount",
        type=float,
        default=25_000.0,
        help="Minimum daily amount filter (same unit as parquet field, default: 25000)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="logs/factor_analysis",
        help="Output directory for CSV/JSON",
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


def _calc_list_days(trade_date: str, list_date: str) -> int:
    if not trade_date or not list_date or len(list_date) != 8:
        return 0
    try:
        return (pd.Timestamp(trade_date) - pd.Timestamp(list_date)).days
    except Exception:
        return 0


def _safe_corr(a: pd.Series, b: pd.Series, method: str) -> float:
    if a.empty or b.empty:
        return 0.0
    value = a.corr(b, method=method)
    return _to_float(value, 0.0)


def _bucket_by_score(scores: pd.Series, bins: int) -> pd.Series:
    ranked = scores.rank(method="first")
    return pd.qcut(ranked, q=bins, labels=False) + 1


def _effective_score(raw_score: Any, direction: str) -> float:
    value = _to_float(raw_score, 0.0)
    if direction == "reverse":
        value = 100.0 - value
    if value < 0:
        return 0.0
    if value > 100:
        return 100.0
    return value


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    args = parse_args()

    start_date = normalize_date(args.start_date)
    end_date = normalize_date(args.end_date)
    deciles = max(args.deciles, 2)
    top_k = max(args.top_k, 1)
    min_list_days = max(args.min_list_days, 0)
    min_amount = max(float(args.min_amount), 0.0)

    open_dates = list_open_trade_dates(start_date=start_date, end_date=end_date)
    if len(open_dates) < 2:
        raise ValueError("not enough trading days in selected range")

    strategy = load_strategy(args.strategy_key)
    universe_df = list_stock_universe()
    if universe_df.empty:
        raise ValueError("stock universe is empty")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info(
        "factor_analysis start: strategy=%s, start=%s, end=%s, days=%s, deciles=%s, top_k=%s",
        args.strategy_key,
        start_date,
        end_date,
        len(open_dates),
        deciles,
        top_k,
    )

    daily_rows: list[dict[str, Any]] = []
    prev_top_set: set[str] | None = None

    progress = tqdm(open_dates[:-1], total=len(open_dates) - 1, desc="factor_analysis", unit="day", dynamic_ncols=True)
    for idx, trade_date in enumerate(progress):
        next_trade_date = open_dates[idx + 1]
        bundle = load_daily_data_bundle(
            trade_date=trade_date,
            next_trade_date=next_trade_date,
            universe_df=universe_df,
        )
        frame = bundle.frame_t.copy()
        if frame.empty:
            progress.set_postfix(date=trade_date, status="empty")
            continue

        frame["list_days"] = frame.apply(
            lambda row: _calc_list_days(trade_date, str(row.get("list_date") or "")),
            axis=1,
        )
        frame = frame[frame["list_days"] >= min_list_days]
        frame = frame[frame["amount"].fillna(0) >= min_amount]
        frame = frame[frame["close"].notna() & frame["open"].notna()]
        if frame.empty:
            progress.set_postfix(date=trade_date, status="filtered_empty")
            continue

        sector_strength_map = build_sector_strength_map(bundle.sector_rows_t)
        frame["sector_strength"] = frame["industry"].map(sector_strength_map).fillna(50.0)

        context = StrategyContext(
            trade_date=trade_date,
            frame=frame,
            market_regime="neutral",
            market_exposure=1.0,
            params={},
        )
        scored = strategy.score(context)
        if scored is None or scored.empty:
            progress.set_postfix(date=trade_date, status="score_empty")
            continue

        scored["raw_score"] = scored.get("total_score", 0).fillna(0.0)
        scored["score"] = scored["raw_score"].apply(lambda x: _effective_score(x, args.score_direction))
        next_close_map = {
            str(item.get("ts_code") or ""): _to_float(item.get("close"))
            for item in bundle.frame_t1.to_dict(orient="records")
        }
        scored["next_close"] = scored["ts_code"].map(next_close_map)
        scored["fwd1_ret"] = scored.apply(
            lambda row: (_to_float(row.get("next_close")) / _to_float(row.get("close")) - 1.0)
            if _to_float(row.get("next_close")) > 0 and _to_float(row.get("close")) > 0
            else np.nan,
            axis=1,
        )
        scored = scored.dropna(subset=["score", "fwd1_ret"])
        if len(scored) < deciles:
            progress.set_postfix(date=trade_date, status="too_few", n=len(scored))
            continue

        scored["bucket"] = _bucket_by_score(scored["score"], deciles)
        bucket_ret = scored.groupby("bucket", as_index=False)["fwd1_ret"].mean()
        bucket_map = {int(row["bucket"]): _to_float(row["fwd1_ret"]) for row in bucket_ret.to_dict(orient="records")}

        top_bucket_ret = _to_float(bucket_map.get(deciles), 0.0)
        bottom_bucket_ret = _to_float(bucket_map.get(1), 0.0)
        ls_ret = top_bucket_ret - bottom_bucket_ret

        pearson_ic = _safe_corr(scored["score"], scored["fwd1_ret"], method="pearson")
        rank_ic = _safe_corr(scored["score"], scored["fwd1_ret"], method="spearman")

        top_codes = (
            scored.sort_values(by=["score", "ts_code"], ascending=[False, True])
            .head(top_k)["ts_code"]
            .astype(str)
        )
        top_set = set(top_codes.tolist())
        turnover = 0.0
        if prev_top_set is not None and top_set:
            overlap = len(prev_top_set & top_set)
            turnover = 1.0 - overlap / max(len(top_set), 1)
        prev_top_set = top_set

        row: dict[str, Any] = {
            "trade_date": trade_date,
            "next_trade_date": next_trade_date,
            "sample_size": int(len(scored)),
            "pearson_ic": pearson_ic,
            "rank_ic": rank_ic,
            "top_bucket_ret": top_bucket_ret,
            "bottom_bucket_ret": bottom_bucket_ret,
            "long_short_ret": ls_ret,
            "top_k_turnover": turnover,
        }
        for bucket in range(1, deciles + 1):
            row[f"bucket_{bucket}_ret"] = _to_float(bucket_map.get(bucket), 0.0)
        daily_rows.append(row)
        progress.set_postfix(date=trade_date, sample=len(scored), ic=f"{rank_ic:.4f}", ls=f"{ls_ret:.4f}")

    if not daily_rows:
        raise ValueError("no valid rows generated; please relax filters or check data range")

    daily_df = pd.DataFrame(daily_rows).sort_values("trade_date")
    long_short_curve = (1.0 + daily_df["long_short_ret"]).cumprod()
    top_curve = (1.0 + daily_df["top_bucket_ret"]).cumprod()
    bottom_curve = (1.0 + daily_df["bottom_bucket_ret"]).cumprod()

    summary = {
        "strategy_key": args.strategy_key,
        "score_direction": args.score_direction,
        "start_date": start_date,
        "end_date": end_date,
        "days": int(len(daily_df)),
        "mean_pearson_ic": _to_float(daily_df["pearson_ic"].mean()),
        "mean_rank_ic": _to_float(daily_df["rank_ic"].mean()),
        "ic_positive_ratio": _to_float((daily_df["rank_ic"] > 0).mean()),
        "mean_top_bucket_ret": _to_float(daily_df["top_bucket_ret"].mean()),
        "mean_bottom_bucket_ret": _to_float(daily_df["bottom_bucket_ret"].mean()),
        "mean_long_short_ret": _to_float(daily_df["long_short_ret"].mean()),
        "long_short_win_rate": _to_float((daily_df["long_short_ret"] > 0).mean()),
        "long_short_cum_return": _to_float(long_short_curve.iloc[-1] - 1.0),
        "top_bucket_cum_return": _to_float(top_curve.iloc[-1] - 1.0),
        "bottom_bucket_cum_return": _to_float(bottom_curve.iloc[-1] - 1.0),
        "avg_top_k_turnover": _to_float(daily_df["top_k_turnover"].mean()),
        "median_top_k_turnover": _to_float(daily_df["top_k_turnover"].median()),
        "top_k": top_k,
        "deciles": deciles,
        "min_list_days": min_list_days,
        "min_amount": min_amount,
    }

    suffix = f"{args.strategy_key}_{args.score_direction}_{start_date}_{end_date}"
    csv_path = output_dir / f"daily_metrics_{suffix}.csv"
    json_path = output_dir / f"summary_{suffix}.json"
    daily_df.to_csv(csv_path, index=False)
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    logger.info("factor_analysis done: days=%s", summary["days"])
    logger.info("mean_rank_ic=%.6f, mean_pearson_ic=%.6f", summary["mean_rank_ic"], summary["mean_pearson_ic"])
    logger.info(
        "long_short: mean=%.6f, win_rate=%.4f, cum=%.4f",
        summary["mean_long_short_ret"],
        summary["long_short_win_rate"],
        summary["long_short_cum_return"],
    )
    logger.info(
        "top_vs_bottom cum: top=%.4f, bottom=%.4f",
        summary["top_bucket_cum_return"],
        summary["bottom_bucket_cum_return"],
    )
    logger.info("turnover(top_k=%s): avg=%.4f, median=%.4f", top_k, summary["avg_top_k_turnover"], summary["median_top_k_turnover"])
    logger.info("output: %s", csv_path)
    logger.info("output: %s", json_path)


if __name__ == "__main__":
    main()
