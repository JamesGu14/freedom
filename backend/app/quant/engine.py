from __future__ import annotations

import datetime as dt
import logging
import math
from collections import deque
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from app.data.duckdb_backtest_store import list_open_trade_dates, list_stock_universe, normalize_date
from app.data.tushare_client import fetch_index_weight
from app.data.mongo_backtest import (
    clear_backtest_run_details,
    update_backtest_run,
    upsert_backtest_nav,
    upsert_backtest_positions,
    upsert_backtest_signals,
    upsert_backtest_trades,
)
from app.quant.allocator import calc_target_amount, calc_target_weight, pick_worst_holding, should_rotate
from app.quant.base import StrategyContext, StrategyProtocol
from app.quant.context import load_daily_data_bundle
from app.quant.execution import execute_orders
from app.quant.factors_market import classify_market_regime
from app.quant.factors_sector import build_sector_strength_maps
from app.quant.metrics import build_summary_metrics
from app.quant.portfolio import PortfolioState

logger = logging.getLogger(__name__)


DEFAULT_BACKTEST_PARAMS: dict[str, Any] = {
    "buy_threshold": 75.0,
    "sell_threshold": 50.0,
    "stop_loss_pct": 0.08,
    "trail_stop_pct": 0.10,
    "max_hold_days": 40,
    "min_avg_amount_20d": 25_000.0,
    "max_positions": 5,
    "slot_weight": 0.20,
    "market_exposure": {"risk_on": 1.0, "neutral": 0.7, "risk_off": 0.4},
    "rotate_score_delta": 8.0,
    "rotate_profit_ceiling": 0.05,
    "min_hold_days_before_rotate": 3,
    "sector_max": 0.40,
    "sell_confirm_days": 1,
    "signal_store_topk": 100,
    "score_direction": "normal",
    "factor_weights": {
        "stock_trend": 0.35,
        "sector_strength": 0.25,
        "value_quality": 0.25,
        "liquidity_stability": 0.15,
    },
    "enable_buy_tech_filter": True,
    "entry_require_trend_alignment": False,
    "entry_require_macd_positive": False,
    "entry_min_sector_strength": 0.0,
    "entry_sector_strength_quantile": 0.0,
    "entry_rsi_min": 0.0,
    "entry_rsi_max": 100.0,
    "entry_max_pct_chg": 100.0,
    "allowed_boards": ["sh_main", "sz_main", "star", "gem"],
    "score_ceiling": 100.0,
    "slot_min_scale": 0.6,
    "min_gross_exposure": 0.0,
    "market_exposure_floor": 0.4,
    "allow_buy_in_risk_off": True,
    "use_member_sector_mapping": True,
    "sector_source_weights": {"sw": 0.6, "ci": 0.4},
    "max_daily_buy_count": 99,
    "max_daily_sell_count": 99,
    "max_daily_trade_count": 99,
    "max_daily_rotate_count": 99,
    "reentry_cooldown_days": 0,
    "annual_trade_window_days": 252,
    "max_annual_trade_count": 0,
    "max_annual_buy_count": 0,
    "max_annual_sell_count": 0,
}


@dataclass(slots=True)
class BacktestRunConfig:
    run_id: str
    strategy_id: str
    strategy_version_id: str
    start_date: str
    end_date: str
    initial_capital: float = 1_000_000.0
    params_snapshot: dict[str, Any] | None = None


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


def _to_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _to_int(value: Any, default: int = 0) -> int:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_allowed_boards(value: Any) -> set[str]:
    default = {"sh_main", "sz_main", "star", "gem"}
    if value is None:
        return default
    if isinstance(value, str):
        tokens = [item.strip().lower() for item in value.split(",")]
    elif isinstance(value, (list, tuple, set)):
        tokens = [str(item).strip().lower() for item in value]
    else:
        return default
    allowed = {item for item in tokens if item}
    if not allowed:
        return default
    valid = {"sh_main", "sz_main", "star", "gem", "bse", "other"}
    filtered = {item for item in allowed if item in valid}
    return filtered or default


def _infer_board(ts_code: Any) -> str:
    text = str(ts_code or "").strip().upper()
    if not text or "." not in text:
        return "other"
    code, suffix = text.split(".", 1)
    if suffix == "BJ":
        return "bse"
    if suffix == "SH":
        if code.startswith(("688", "689")):
            return "star"
        if code.startswith(("600", "601", "603", "605")):
            return "sh_main"
        return "other"
    if suffix == "SZ":
        if code.startswith(("300", "301")):
            return "gem"
        if code.startswith(("000", "001", "002", "003")):
            return "sz_main"
        return "other"
    return "other"


def _trade_date_to_dt(value: str) -> dt.datetime:
    return dt.datetime.strptime(value, "%Y%m%d")


def _calc_list_days(trade_date: str, list_date: str) -> int:
    if not trade_date or not list_date or len(str(list_date)) != 8:
        return 0
    try:
        return (_trade_date_to_dt(trade_date) - _trade_date_to_dt(str(list_date))).days
    except ValueError:
        return 0


def _normalize_score_direction(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"reverse", "inverse", "contrarian", "contra"}:
        return "reverse"
    return "normal"


def _effective_score(raw_score: Any, direction: str) -> float:
    score = _to_float(raw_score, 0.0)
    if direction == "reverse":
        score = 100.0 - score
    if score < 0.0:
        return 0.0
    if score > 100.0:
        return 100.0
    return score


def _normalize_limit(value: Any, default: int) -> int:
    result = _to_int(value, default)
    return max(result, 0)


def _normalize_sector_source_weights(value: Any) -> dict[str, float]:
    default = {"sw": 0.6, "ci": 0.4}
    if not isinstance(value, dict):
        return default
    sw = max(_to_float(value.get("sw"), default["sw"]), 0.0)
    ci = max(_to_float(value.get("ci"), default["ci"]), 0.0)
    if sw + ci <= 0:
        return default
    total = sw + ci
    return {
        "sw": sw / total,
        "ci": ci / total,
    }


def _normalize_index_code(value: Any) -> str:
    text = str(value or "").strip().upper()
    if not text:
        return ""
    if "." in text:
        return text
    return f"{text}.SH"


def _load_index_member_codes(*, index_code: str, start_date: str, end_date: str) -> set[str]:
    normalized_code = _normalize_index_code(index_code)
    if not normalized_code:
        return set()
    try:
        df = fetch_index_weight(index_code=normalized_code, start_date=start_date, end_date=end_date)
    except Exception as exc:  # noqa: BLE001
        logger.warning("load index members failed index=%s: %s", normalized_code, exc)
        return set()
    if df is None or df.empty:
        logger.warning("index members empty index=%s in range=%s-%s", normalized_code, start_date, end_date)
        return set()
    source_col = "con_code" if "con_code" in df.columns else ("ts_code" if "ts_code" in df.columns else "")
    if not source_col:
        logger.warning("index members missing con_code/ts_code index=%s", normalized_code)
        return set()
    codes = {str(item).strip().upper() for item in df[source_col].dropna().tolist() if str(item).strip()}
    return codes


def _resolve_sector_strength(
    *,
    ts_code: Any,
    industry_name: Any,
    shenwan_member_codes_map: dict[str, list[str]],
    citic_member_codes_map: dict[str, list[str]],
    sector_strength_name_map: dict[str, float],
    sector_strength_sw_map: dict[str, float],
    sector_strength_ci_map: dict[str, float],
    source_weights: dict[str, float],
) -> float:
    ts_code_text = str(ts_code or "").strip().upper()
    sw_codes = shenwan_member_codes_map.get(ts_code_text, [])
    ci_codes = citic_member_codes_map.get(ts_code_text, [])

    sw_scores = [sector_strength_sw_map.get(code) for code in sw_codes if code in sector_strength_sw_map]
    ci_scores = [sector_strength_ci_map.get(code) for code in ci_codes if code in sector_strength_ci_map]

    sw_avg = (sum(sw_scores) / len(sw_scores)) if sw_scores else None
    ci_avg = (sum(ci_scores) / len(ci_scores)) if ci_scores else None
    if sw_avg is not None and ci_avg is not None:
        sw_weight = max(_to_float(source_weights.get("sw"), 0.6), 0.0)
        ci_weight = max(_to_float(source_weights.get("ci"), 0.4), 0.0)
        total = sw_weight + ci_weight
        if total <= 0:
            return (sw_avg + ci_avg) / 2.0
        return (sw_avg * sw_weight + ci_avg * ci_weight) / total
    if sw_avg is not None:
        return sw_avg
    if ci_avg is not None:
        return ci_avg
    return _to_float(sector_strength_name_map.get(str(industry_name or "").strip()), 50.0)


def _sell_order_priority(order: dict[str, Any]) -> tuple[int, float]:
    reasons = {str(item) for item in (order.get("reason_codes") or [])}
    if "stop_loss" in reasons or "trail_stop" in reasons:
        return (0, _to_float(order.get("score"), 0.0))
    if "max_hold" in reasons:
        return (1, _to_float(order.get("score"), 0.0))
    if "rotate_out" in reasons:
        return (2, _to_float(order.get("score"), 0.0))
    return (3, _to_float(order.get("score"), 0.0))


def _append_reason_code(signal_rows: dict[str, dict[str, Any]], *, ts_code: str, reason_code: str) -> None:
    row = signal_rows.get(ts_code)
    if not row:
        return
    reason_codes = list(row.get("reason_codes") or [])
    if reason_code not in reason_codes:
        reason_codes.append(reason_code)
    row["signal"] = "HOLD"
    row["reason_codes"] = reason_codes


def _throttle_sell_orders(
    *,
    sell_orders: list[dict[str, Any]],
    signal_rows: dict[str, dict[str, Any]],
    limit: int,
    reason_code: str,
) -> list[dict[str, Any]]:
    if limit < 0 or len(sell_orders) <= limit:
        return sell_orders
    sorted_orders = sorted(sell_orders, key=_sell_order_priority)
    keep_orders = sorted_orders[:limit]
    keep_codes = {str(item.get("ts_code") or "") for item in keep_orders}
    for item in sell_orders:
        ts_code = str(item.get("ts_code") or "")
        if ts_code and ts_code not in keep_codes:
            _append_reason_code(signal_rows, ts_code=ts_code, reason_code=reason_code)
    return keep_orders


def _normalize_quantile(value: Any) -> float:
    quantile = _to_float(value, 0.0)
    if quantile > 1.0 and quantile <= 100.0:
        quantile = quantile / 100.0
    return max(min(quantile, 1.0), 0.0)


def _apply_buy_quality_filters(
    candidates: pd.DataFrame,
    params: dict[str, Any],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    meta: dict[str, Any] = {"sector_strength_quantile_threshold": None}
    if candidates is None or candidates.empty:
        return pd.DataFrame(), meta
    data = candidates
    if _to_bool(params.get("entry_require_trend_alignment"), False):
        data = data[
            (data["close"].fillna(0) > data["ma20"].fillna(0))
            & (data["ma20"].fillna(0) > data["ma60"].fillna(0))
        ]
    if _to_bool(params.get("entry_require_macd_positive"), False):
        data = data[data["macd_hist"].fillna(0) > 0]
    if _to_bool(params.get("entry_require_macd_zero_axis_cross"), False):
        macd = pd.to_numeric(data.get("macd", pd.Series(0.0, index=data.index)), errors="coerce").fillna(0.0)
        macd_signal = pd.to_numeric(
            data.get("macd_signal", pd.Series(0.0, index=data.index)),
            errors="coerce",
        ).fillna(0.0)
        macd_hist = pd.to_numeric(data.get("macd_hist", pd.Series(0.0, index=data.index)), errors="coerce").fillna(0.0)
        data = data[
            (macd_hist > 0)
            & (macd < 0)
            & (macd_signal < 0)
        ]

    min_sector_strength = max(_to_float(params.get("entry_min_sector_strength"), 0.0), 0.0)
    if min_sector_strength > 0:
        data = data[data["sector_strength"].fillna(0) >= min_sector_strength]

    sector_quantile = _normalize_quantile(params.get("entry_sector_strength_quantile"))
    if sector_quantile > 0 and not data.empty:
        threshold = _to_float(data["sector_strength"].fillna(0.0).quantile(sector_quantile), 0.0)
        meta["sector_strength_quantile_threshold"] = threshold
        data = data[data["sector_strength"].fillna(0.0) >= threshold]

    rsi_min = _to_float(params.get("entry_rsi_min"), 0.0)
    rsi_max = _to_float(params.get("entry_rsi_max"), 100.0)
    low, high = min(rsi_min, rsi_max), max(rsi_min, rsi_max)
    if low > 0.0 or high < 100.0:
        data = data[(data["rsi12"].fillna(50.0) >= low) & (data["rsi12"].fillna(50.0) <= high)]

    max_pct_chg = _to_float(params.get("entry_max_pct_chg"), 100.0)
    if max_pct_chg < 100:
        data = data[data["pct_chg"].fillna(0) <= max_pct_chg]
    return data, meta


def _build_buy_reason_codes(
    *,
    row: dict[str, Any],
    params: dict[str, Any],
    is_rotate_buy: bool,
    buy_filter_meta: dict[str, Any],
) -> list[str]:
    reason_codes: list[str] = ["score_rank"]

    def _push(code: str) -> None:
        if code and code not in reason_codes:
            reason_codes.append(code)

    if is_rotate_buy:
        _push("rotate_in")

    if _to_bool(params.get("entry_require_trend_alignment"), False):
        close = _to_float(row.get("close"), 0.0)
        ma20 = _to_float(row.get("ma20"), 0.0)
        ma60 = _to_float(row.get("ma60"), 0.0)
        if close > ma20 > ma60:
            _push("trend_alignment_pass")

    if _to_bool(params.get("entry_require_macd_positive"), False) and _to_float(row.get("macd_hist"), 0.0) > 0:
        _push("macd_positive")
    if (
        _to_float(row.get("macd_hist"), 0.0) > 0
        and _to_float(row.get("macd"), 0.0) < 0
        and _to_float(row.get("macd_signal"), 0.0) < 0
    ):
        _push("macd_zero_axis_golden_cross")

    min_sector_strength = max(_to_float(params.get("entry_min_sector_strength"), 0.0), 0.0)
    sector_strength = _to_float(row.get("sector_strength"), 0.0)
    if min_sector_strength > 0 and sector_strength >= min_sector_strength:
        _push("sector_strength_min_pass")

    sector_quantile = _normalize_quantile(params.get("entry_sector_strength_quantile"))
    threshold = buy_filter_meta.get("sector_strength_quantile_threshold")
    if sector_quantile > 0 and threshold is not None and sector_strength >= _to_float(threshold, 0.0):
        _push("sector_strength_quantile_pass")

    rsi_min = _to_float(params.get("entry_rsi_min"), 0.0)
    rsi_max = _to_float(params.get("entry_rsi_max"), 100.0)
    low, high = min(rsi_min, rsi_max), max(rsi_min, rsi_max)
    if low > 0.0 or high < 100.0:
        rsi12 = _to_float(row.get("rsi12"), 50.0)
        if low <= rsi12 <= high:
            _push("rsi_range_pass")

    max_pct_chg = _to_float(params.get("entry_max_pct_chg"), 100.0)
    if max_pct_chg < 100 and _to_float(row.get("pct_chg"), 0.0) <= max_pct_chg:
        _push("pct_chg_cap_pass")
    return reason_codes


def _apply_min_gross_exposure(
    *,
    buy_orders: list[dict[str, Any]],
    sell_orders: list[dict[str, Any]],
    portfolio: PortfolioState,
    close_map: dict[str, float],
    total_equity: float,
    min_gross_exposure: float,
    per_position_cap: float,
) -> None:
    if total_equity <= 0 or min_gross_exposure <= 0 or not buy_orders:
        return
    target_exposure = max(min(min_gross_exposure, 1.0), 0.0)
    cap = max(min(per_position_cap, 1.0), 0.0)
    if cap <= 0:
        return

    sold_codes = {str(item.get("ts_code") or "") for item in sell_orders if str(item.get("side") or "") == "SELL"}
    remaining_position_value = 0.0
    for ts_code, position in portfolio.positions.items():
        if ts_code in sold_codes:
            continue
        close = _to_float(close_map.get(ts_code), 0.0)
        if close <= 0:
            continue
        remaining_position_value += close * float(position.qty)

    current_exposure = remaining_position_value / total_equity if total_equity > 0 else 0.0
    planned_buy_weight = sum(_to_float(item.get("target_weight"), 0.0) for item in buy_orders)
    shortfall = target_exposure - (current_exposure + planned_buy_weight)
    if shortfall <= 0:
        return

    ranked_orders = sorted(buy_orders, key=lambda item: _to_float(item.get("score"), 0.0), reverse=True)
    for order in ranked_orders:
        if shortfall <= 0:
            break
        current_weight = _to_float(order.get("target_weight"), 0.0)
        headroom = max(cap - current_weight, 0.0)
        if headroom <= 0:
            continue
        add_weight = min(headroom, shortfall)
        new_weight = current_weight + add_weight
        order["target_weight"] = new_weight
        order["target_amount"] = calc_target_amount(total_equity=total_equity, target_weight=new_weight)
        shortfall -= add_weight


class BacktestEngine:
    def __init__(self, strategy: StrategyProtocol):
        self.strategy = strategy

    def _merge_params(self, params_snapshot: dict[str, Any] | None) -> dict[str, Any]:
        merged = dict(DEFAULT_BACKTEST_PARAMS)
        if params_snapshot:
            for key, value in params_snapshot.items():
                merged[key] = value
        return merged

    def run(self, config: BacktestRunConfig) -> dict[str, Any]:
        start_date = normalize_date(config.start_date)
        end_date = normalize_date(config.end_date)
        params = self._merge_params(config.params_snapshot)
        score_direction = _normalize_score_direction(params.get("score_direction"))
        allowed_boards = _normalize_allowed_boards(params.get("allowed_boards"))
        initial_capital = float(config.initial_capital)
        run_id = config.run_id

        update_backtest_run(run_id=run_id, status="running", error_message="", summary_metrics={})
        clear_backtest_run_details(run_id)

        open_dates = list_open_trade_dates(start_date=start_date, end_date=end_date)
        if len(open_dates) < 2:
            raise ValueError(f"not enough trading days in range: {start_date} - {end_date}")

        universe_df = list_stock_universe()
        if universe_df.empty:
            raise ValueError("stock universe is empty")
        universe_index_code = _normalize_index_code(params.get("universe_index_code"))
        if universe_index_code:
            member_codes = _load_index_member_codes(
                index_code=universe_index_code,
                start_date=start_date,
                end_date=end_date,
            )
            if member_codes:
                universe_df = universe_df[universe_df["ts_code"].isin(member_codes)].copy()
                logger.info("universe filtered by index=%s members=%s", universe_index_code, len(member_codes))
            else:
                logger.warning("universe filter skipped: index=%s has no members", universe_index_code)
        if universe_df.empty:
            raise ValueError("stock universe is empty after index filter")

        trade_index_map = {trade_date: idx for idx, trade_date in enumerate(open_dates)}
        portfolio = PortfolioState(initial_capital=initial_capital, cash=initial_capital, positions={})
        peak_nav = 1.0
        sell_confirm_days = max(int(params.get("sell_confirm_days", 1) or 1), 1)
        signal_store_topk = max(int(params.get("signal_store_topk", 100) or 0), 0)
        min_gross_exposure = max(min(_to_float(params.get("min_gross_exposure"), 0.0), 1.0), 0.0)
        use_member_sector_mapping = _to_bool(params.get("use_member_sector_mapping"), True)
        sector_source_weights = _normalize_sector_source_weights(params.get("sector_source_weights"))
        max_daily_buy_count = _normalize_limit(params.get("max_daily_buy_count"), 99)
        max_daily_sell_count = _normalize_limit(params.get("max_daily_sell_count"), 99)
        max_daily_trade_count = _normalize_limit(params.get("max_daily_trade_count"), 99)
        max_daily_rotate_count = _normalize_limit(params.get("max_daily_rotate_count"), 99)
        reentry_cooldown_days = max(_to_int(params.get("reentry_cooldown_days"), 0), 0)
        market_exposure_floor = max(min(_to_float(params.get("market_exposure_floor"), 0.4), 1.0), 0.0)
        allow_buy_in_risk_off = _to_bool(params.get("allow_buy_in_risk_off"), True)
        annual_trade_window_days = max(_to_int(params.get("annual_trade_window_days"), 252), 1)
        max_annual_trade_count = _normalize_limit(params.get("max_annual_trade_count"), 0)
        max_annual_buy_count = _normalize_limit(params.get("max_annual_buy_count"), 0)
        max_annual_sell_count = _normalize_limit(params.get("max_annual_sell_count"), 0)
        sell_signal_streak: dict[str, int] = {}
        last_exit_trade_index: dict[str, int] = {}
        trade_events: deque[tuple[int, str]] = deque()
        market_pct_history: list[float] = []
        logger.info(
            "run config: score_direction=%s, allowed_boards=%s, min_gross_exposure=%.2f, member_sector_mapping=%s, buy_limit=%s, sell_limit=%s, trade_limit=%s, rotate_limit=%s, reentry_cooldown=%s, exposure_floor=%.2f, buy_in_risk_off=%s, annual_window=%s, annual_trade_cap=%s",
            score_direction,
            ",".join(sorted(allowed_boards)),
            min_gross_exposure,
            use_member_sector_mapping,
            max_daily_buy_count,
            max_daily_sell_count,
            max_daily_trade_count,
            max_daily_rotate_count,
            reentry_cooldown_days,
            market_exposure_floor,
            allow_buy_in_risk_off,
            annual_trade_window_days,
            max_annual_trade_count,
        )

        nav_rows: list[dict[str, Any]] = []
        all_trades: list[dict[str, Any]] = []

        for idx, trade_date in enumerate(open_dates[:-1], start=1):
            next_trade_date = open_dates[idx]
            execution_trade_index = trade_index_map.get(next_trade_date, idx)
            window_start_index = execution_trade_index - annual_trade_window_days + 1
            while trade_events and trade_events[0][0] < window_start_index:
                trade_events.popleft()

            annual_trade_budget = -1
            annual_buy_budget = -1
            annual_sell_budget = -1
            if max_annual_trade_count > 0 or max_annual_buy_count > 0 or max_annual_sell_count > 0:
                rolling_trade_count = len(trade_events)
                rolling_buy_count = sum(1 for _, side in trade_events if side == "BUY")
                rolling_sell_count = rolling_trade_count - rolling_buy_count
                if max_annual_trade_count > 0:
                    annual_trade_budget = max(max_annual_trade_count - rolling_trade_count, 0)
                if max_annual_buy_count > 0:
                    annual_buy_budget = max(max_annual_buy_count - rolling_buy_count, 0)
                if max_annual_sell_count > 0:
                    annual_sell_budget = max(max_annual_sell_count - rolling_sell_count, 0)

            bundle = load_daily_data_bundle(
                trade_date=trade_date,
                next_trade_date=next_trade_date,
                universe_df=universe_df,
            )
            if bundle.frame_t.empty:
                logger.info("[%s/%s] %s frame empty, skip", idx, len(open_dates) - 1, trade_date)
                continue

            market_row = bundle.market_factor_t or {}
            market_regime, exposure = classify_market_regime(
                market_row,
                recent_pct_changes=market_pct_history,
            )
            market_pct_history.append(_to_float(market_row.get("pct_change"), 0.0))
            if len(market_pct_history) > 40:
                market_pct_history = market_pct_history[-40:]
            exposure_map = dict(params.get("market_exposure") or {})
            market_exposure = _to_float(exposure_map.get(market_regime), exposure)
            if market_exposure < market_exposure_floor:
                market_exposure = market_exposure_floor

            frame = bundle.frame_t.copy()
            frame["board"] = frame["ts_code"].map(_infer_board)
            frame = frame[frame["board"].isin(allowed_boards)]
            frame["list_days"] = frame.apply(
                lambda row: _calc_list_days(trade_date, str(row.get("list_date") or "")),
                axis=1,
            )
            frame = frame[frame["list_days"] >= 120]
            frame = frame[frame["amount"].fillna(0) >= _to_float(params.get("min_avg_amount_20d"), 25_000.0)]
            frame = frame[frame["close"].notna() & frame["open"].notna()]
            if frame.empty:
                logger.info("[%s/%s] %s no candidates after filters", idx, len(open_dates) - 1, trade_date)
                continue

            sector_strength_maps = build_sector_strength_maps(bundle.sector_rows_t)
            sector_strength_name_map = sector_strength_maps.get("name", {})
            sector_strength_sw_map = sector_strength_maps.get("sw_code", {})
            sector_strength_ci_map = sector_strength_maps.get("ci_code", {})
            shenwan_member_codes_map = bundle.shenwan_member_codes_t or {}
            citic_member_codes_map = bundle.citic_member_codes_t or {}
            if use_member_sector_mapping:
                frame["sector_strength"] = frame.apply(
                    lambda row: _resolve_sector_strength(
                        ts_code=row.get("ts_code"),
                        industry_name=row.get("industry"),
                        shenwan_member_codes_map=shenwan_member_codes_map,
                        citic_member_codes_map=citic_member_codes_map,
                        sector_strength_name_map=sector_strength_name_map,
                        sector_strength_sw_map=sector_strength_sw_map,
                        sector_strength_ci_map=sector_strength_ci_map,
                        source_weights=sector_source_weights,
                    ),
                    axis=1,
                )
            else:
                frame["sector_strength"] = frame["industry"].map(sector_strength_name_map).fillna(50.0)

            strategy_context = StrategyContext(
                trade_date=trade_date,
                frame=frame,
                market_regime=market_regime,
                market_exposure=market_exposure,
                params=params,
            )
            scored = self.strategy.score(strategy_context)
            if scored.empty:
                logger.info("[%s/%s] %s score empty", idx, len(open_dates) - 1, trade_date)
                continue

            scored["raw_score"] = scored.get("total_score", 0).fillna(0.0)
            scored["score"] = scored["raw_score"].apply(lambda x: _effective_score(x, score_direction))
            scored_map = {
                str(row["ts_code"]): row
                for row in scored[
                    [
                        "ts_code",
                        "score",
                        "raw_score",
                        "close",
                        "ma20",
                        "macd_hist",
                        "kdj_k",
                        "kdj_d",
                        "kdj_j",
                        "boll_middle",
                        "boll_lower",
                    ]
                ].to_dict(orient="records")
            }
            close_map_t = {str(row["ts_code"]): _to_float(row.get("close")) for row in scored.to_dict(orient="records")}
            portfolio.update_max_price(close_map_t)
            total_equity_t = portfolio.total_equity(close_map_t)

            signal_rows: dict[str, dict[str, Any]] = {}
            for row in scored.to_dict(orient="records"):
                ts_code = str(row.get("ts_code") or "")
                if not ts_code:
                    continue
                signal_rows[ts_code] = {
                    "run_id": run_id,
                    "trade_date": trade_date,
                    "ts_code": ts_code,
                    "signal": "HOLD",
                    "score": _to_float(row.get("score")),
                    "raw_score": _to_float(row.get("raw_score")),
                    "target_weight": 0.0,
                    "target_amount": 0.0,
                    "reason_codes": [],
                    "market_regime": market_regime,
                }

            sell_orders: list[dict[str, Any]] = []
            holding_scores: list[dict[str, Any]] = []
            for ts_code, position in list(portfolio.positions.items()):
                row = scored_map.get(ts_code, {})
                close = _to_float(row.get("close"))
                score = _to_float(row.get("score"))
                raw_score = _to_float(row.get("raw_score"))
                ma20 = _to_float(row.get("ma20"))
                macd_hist = _to_float(row.get("macd_hist"))
                kdj_k = _to_float(row.get("kdj_k"))
                kdj_d = _to_float(row.get("kdj_d"))
                kdj_j = _to_float(row.get("kdj_j"))
                boll_middle = _to_float(row.get("boll_middle"))
                boll_lower = _to_float(row.get("boll_lower"))
                holding_days = max(trade_index_map.get(trade_date, 0) - position.buy_trade_index, 0)
                profit_pct = (close / position.cost_price - 1.0) if position.cost_price > 0 and close > 0 else 0.0
                reasons: list[str] = []
                if close > 0 and ma20 > 0 and close < ma20 and macd_hist < 0:
                    reasons.append("trend_break")
                if close > 0 and boll_middle > 0 and close < boll_middle and kdj_k < kdj_d:
                    reasons.append("boll_break")
                if close > 0 and boll_lower > 0 and close < boll_lower:
                    reasons.append("boll_lower_break")
                if kdj_k < kdj_d and kdj_j < kdj_d and score < _to_float(params.get("sell_threshold"), 50.0):
                    reasons.append("kdj_dead_cross")
                if close > 0 and close <= position.cost_price * (1.0 - _to_float(params.get("stop_loss_pct"), 0.08)):
                    reasons.append("stop_loss")
                if close > 0 and close <= position.max_price * (1.0 - _to_float(params.get("trail_stop_pct"), 0.10)):
                    reasons.append("trail_stop")
                if holding_days >= int(params.get("max_hold_days", 40)) and score < _to_float(params.get("sell_threshold"), 50.0):
                    reasons.append("max_hold")
                if reasons:
                    streak = int(sell_signal_streak.get(ts_code, 0) or 0) + 1
                    sell_signal_streak[ts_code] = streak
                    hard_reasons = {"stop_loss", "trail_stop"}
                    require_confirm = (
                        sell_confirm_days > 1
                        and not any(reason in hard_reasons for reason in reasons)
                    )
                    pending_confirm = require_confirm and streak < sell_confirm_days
                    if not pending_confirm:
                        sell_orders.append(
                            {
                                "side": "SELL",
                                "signal_type": "SELL",
                                "ts_code": ts_code,
                                "score": score,
                                "target_weight": 0.0,
                                "target_amount": 0.0,
                                "reason_codes": reasons,
                            }
                        )
                    signal_rows.setdefault(
                        ts_code,
                        {
                            "run_id": run_id,
                            "trade_date": trade_date,
                            "ts_code": ts_code,
                        },
                    ).update(
                        {
                            "signal": "HOLD" if pending_confirm else "SELL",
                            "score": score,
                            "raw_score": raw_score,
                            "target_weight": 0.0,
                            "target_amount": 0.0,
                            "reason_codes": (reasons + ["confirm_pending"]) if pending_confirm else reasons,
                            "confirm_progress": f"{streak}/{sell_confirm_days}" if pending_confirm else "",
                            "market_regime": market_regime,
                        }
                    )
                else:
                    sell_signal_streak[ts_code] = 0
                holding_scores.append(
                    {
                        "ts_code": ts_code,
                        "score": score,
                        "raw_score": raw_score,
                        "profit_pct": profit_pct,
                        "holding_days": holding_days,
                    }
                )

            if max_daily_sell_count > 0:
                sell_orders = _throttle_sell_orders(
                    sell_orders=sell_orders,
                    signal_rows=signal_rows,
                    limit=max_daily_sell_count,
                    reason_code="sell_throttled",
                )
            if max_daily_trade_count > 0:
                sell_orders = _throttle_sell_orders(
                    sell_orders=sell_orders,
                    signal_rows=signal_rows,
                    limit=max_daily_trade_count,
                    reason_code="trade_throttled",
                )
            if annual_sell_budget >= 0:
                sell_orders = _throttle_sell_orders(
                    sell_orders=sell_orders,
                    signal_rows=signal_rows,
                    limit=annual_sell_budget,
                    reason_code="annual_sell_cap",
                )
            if annual_trade_budget >= 0:
                sell_orders = _throttle_sell_orders(
                    sell_orders=sell_orders,
                    signal_rows=signal_rows,
                    limit=annual_trade_budget,
                    reason_code="annual_trade_cap",
                )

            buy_threshold = _to_float(params.get("buy_threshold"), 75.0)
            candidates = scored[(scored["score"] >= buy_threshold) & (~scored["ts_code"].isin(list(portfolio.positions.keys())))]
            if reentry_cooldown_days > 0 and last_exit_trade_index:
                current_trade_index = trade_index_map.get(trade_date, idx)
                blocked_codes = {
                    ts_code
                    for ts_code, exit_trade_index in last_exit_trade_index.items()
                    if current_trade_index - int(exit_trade_index) < reentry_cooldown_days
                }
                if blocked_codes:
                    candidates = candidates[~candidates["ts_code"].isin(list(blocked_codes))]
            enable_buy_tech_filter = _to_bool(params.get("enable_buy_tech_filter"), True)
            if enable_buy_tech_filter:
                candidates = candidates[
                    (candidates["kdj_k"].fillna(0) >= candidates["kdj_d"].fillna(0))
                    & (candidates["close"].fillna(0) >= candidates["boll_middle"].fillna(0))
                    & (
                        (candidates["boll_upper"].fillna(0) <= 0)
                        | (candidates["close"].fillna(0) <= candidates["boll_upper"].fillna(0) * 1.04)
                    )
                ]
            candidates, buy_filter_meta = _apply_buy_quality_filters(candidates, params)
            candidates = candidates.sort_values(by=["score", "sector_strength", "ts_code"], ascending=[False, False, True])

            buy_orders: list[dict[str, Any]] = []
            max_positions = int(params.get("max_positions", 5))
            slot_weight = _to_float(params.get("slot_weight"), 0.20)
            sector_max = _to_float(params.get("sector_max"), 0.40)
            rotate_target_code = ""
            rotate_group_id = ""
            rotate_count_today = 0

            filled_slots_after_sells = portfolio.holding_count() - len({order["ts_code"] for order in sell_orders})
            available_slots = max(max_positions - max(filled_slots_after_sells, 0), 0)
            if max_daily_trade_count > 0:
                available_trade_budget = max(max_daily_trade_count - len(sell_orders), 0)
                if available_trade_budget <= 0:
                    available_slots = 0
            else:
                available_trade_budget = -1
            if annual_trade_budget >= 0:
                annual_trade_budget_after_sells = max(annual_trade_budget - len(sell_orders), 0)
                if available_trade_budget >= 0:
                    available_trade_budget = min(available_trade_budget, annual_trade_budget_after_sells)
                else:
                    available_trade_budget = annual_trade_budget_after_sells
                if available_trade_budget <= 0:
                    available_slots = 0

            buy_count_limit = max_daily_buy_count if max_daily_buy_count > 0 else -1
            if annual_buy_budget >= 0:
                if buy_count_limit >= 0:
                    buy_count_limit = min(buy_count_limit, annual_buy_budget)
                else:
                    buy_count_limit = annual_buy_budget

            # Rotation when full and no explicit sell signal.
            if (
                available_slots <= 0
                and not sell_orders
                and not candidates.empty
                and holding_scores
                and (max_daily_rotate_count <= 0 or rotate_count_today < max_daily_rotate_count)
            ):
                candidate_row = candidates.iloc[0]
                worst = pick_worst_holding(holding_scores)
                if worst and should_rotate(
                    candidate_score=_to_float(candidate_row.get("score")),
                    worst_score=_to_float(worst.get("score")),
                    worst_profit_pct=_to_float(worst.get("profit_pct")),
                    holding_days=int(worst.get("holding_days") or 0),
                    rotate_score_delta=_to_float(params.get("rotate_score_delta"), 8.0),
                    rotate_profit_ceiling=_to_float(params.get("rotate_profit_ceiling"), 0.05),
                    min_hold_days_before_rotate=int(params.get("min_hold_days_before_rotate", 3)),
                ):
                    rotate_group = f"{trade_date}:{worst['ts_code']}->{candidate_row['ts_code']}"
                    rotate_target_code = str(candidate_row["ts_code"])
                    rotate_group_id = rotate_group
                    sell_orders.append(
                        {
                            "side": "SELL",
                            "signal_type": "SELL_ROTATE",
                            "ts_code": str(worst["ts_code"]),
                            "score": _to_float(worst.get("score")),
                            "raw_score": _to_float(worst.get("raw_score")),
                            "target_weight": 0.0,
                            "target_amount": 0.0,
                            "reason_codes": ["rotate_out"],
                            "rotate_group": rotate_group,
                        }
                    )
                    signal_rows.setdefault(
                        str(worst["ts_code"]),
                        {"run_id": run_id, "trade_date": trade_date, "ts_code": str(worst["ts_code"])},
                    ).update(
                        {
                            "signal": "SELL_ROTATE",
                            "score": _to_float(worst.get("score")),
                            "raw_score": _to_float(worst.get("raw_score")),
                            "target_weight": 0.0,
                            "target_amount": 0.0,
                            "reason_codes": ["rotate_out"],
                            "market_regime": market_regime,
                        }
                    )
                    available_slots = 1
                    rotate_count_today += 1
                    if available_trade_budget >= 0:
                        available_trade_budget = max(available_trade_budget - 1, 0)

            allow_new_buy = market_exposure > 0 and (allow_buy_in_risk_off or market_regime != "risk_off")
            if allow_new_buy and available_slots > 0 and not candidates.empty:
                for row in candidates.to_dict(orient="records"):
                    if available_slots <= 0:
                        break
                    if buy_count_limit >= 0 and len(buy_orders) >= buy_count_limit:
                        break
                    if available_trade_budget >= 0 and available_trade_budget <= 0:
                        break
                    ts_code = str(row.get("ts_code") or "")
                    if not ts_code:
                        continue
                    if any(item.get("ts_code") == ts_code for item in buy_orders):
                        continue
                    target_weight = calc_target_weight(
                        score=_to_float(row.get("score")),
                        market_exposure=market_exposure,
                        slot_weight=slot_weight,
                        buy_threshold=buy_threshold,
                        score_ceiling=_to_float(params.get("score_ceiling"), 100.0),
                        slot_min_scale=_to_float(params.get("slot_min_scale"), 0.6),
                        sector_weight=1.0,
                    )
                    target_weight = min(target_weight, sector_max)
                    if target_weight <= 0:
                        continue
                    target_amount = calc_target_amount(total_equity=total_equity_t, target_weight=target_weight)
                    is_rotate_buy = rotate_group_id and ts_code == rotate_target_code
                    signal_type = "BUY_ROTATE" if is_rotate_buy else "BUY"
                    buy_reason_codes = _build_buy_reason_codes(
                        row=row,
                        params=params,
                        is_rotate_buy=bool(is_rotate_buy),
                        buy_filter_meta=buy_filter_meta,
                    )
                    buy_orders.append(
                        {
                            "side": "BUY",
                            "signal_type": signal_type,
                            "ts_code": ts_code,
                            "score": _to_float(row.get("score")),
                            "raw_score": _to_float(row.get("raw_score")),
                            "target_weight": target_weight,
                            "target_amount": target_amount,
                            "reason_codes": buy_reason_codes,
                            "rotate_group": rotate_group_id if is_rotate_buy else "",
                        }
                    )
                    signal_rows.setdefault(
                        ts_code,
                        {"run_id": run_id, "trade_date": trade_date, "ts_code": ts_code},
                    ).update(
                        {
                            "signal": signal_type,
                            "score": _to_float(row.get("score")),
                            "raw_score": _to_float(row.get("raw_score")),
                            "target_weight": target_weight,
                            "target_amount": target_amount,
                            "reason_codes": buy_reason_codes,
                            "market_regime": market_regime,
                        }
                    )
                    available_slots -= 1
                    if available_trade_budget >= 0:
                        available_trade_budget -= 1

            if buy_orders and min_gross_exposure > 0:
                _apply_min_gross_exposure(
                    buy_orders=buy_orders,
                    sell_orders=sell_orders,
                    portfolio=portfolio,
                    close_map=close_map_t,
                    total_equity=total_equity_t,
                    min_gross_exposure=min_gross_exposure,
                    per_position_cap=sector_max,
                )
                for order in buy_orders:
                    ts_code = str(order.get("ts_code") or "")
                    row = signal_rows.get(ts_code)
                    if not row:
                        continue
                    row["target_weight"] = _to_float(order.get("target_weight"))
                    row["target_amount"] = _to_float(order.get("target_amount"))

            orders = sell_orders + buy_orders
            next_daily = bundle.frame_t1
            next_limit = bundle.limit_t1
            trades = execute_orders(
                run_id=run_id,
                signal_trade_date=trade_date,
                execution_trade_date=next_trade_date,
                portfolio=portfolio,
                orders=orders,
                next_daily_df=next_daily,
                next_limit_df=next_limit,
                trade_index=execution_trade_index,
            )
            if trades:
                upsert_backtest_trades(trades)
                all_trades.extend(trades)
                for trade in trades:
                    side = str(trade.get("side") or "").upper()
                    if side in {"BUY", "SELL"}:
                        trade_events.append((execution_trade_index, side))
                    if str(trade.get("side")) == "SELL":
                        trade_ts_code = str(trade.get("ts_code") or "")
                        trade_index_value = _to_int(trade.get("trade_index"), execution_trade_index)
                        if trade_ts_code:
                            last_exit_trade_index[trade_ts_code] = trade_index_value
                        sell_signal_streak.pop(str(trade.get("ts_code") or ""), None)

            close_map_t1 = {}
            if next_daily is not None and not next_daily.empty:
                for row in next_daily.to_dict(orient="records"):
                    ts_code = str(row.get("ts_code") or "")
                    if not ts_code:
                        continue
                    close_map_t1[ts_code] = _to_float(row.get("close"))

            total_equity_t1 = portfolio.total_equity(close_map_t1)
            if not math.isfinite(total_equity_t1):
                logger.warning(
                    "[%s/%s] signal_date=%s exec_date=%s total_equity invalid=%s, fallback to cash",
                    idx,
                    len(open_dates) - 1,
                    trade_date,
                    next_trade_date,
                    total_equity_t1,
                )
                total_equity_t1 = _to_float(portfolio.cash, 0.0)
            nav = (total_equity_t1 / initial_capital) if initial_capital > 0 else 1.0
            nav = _to_float(nav, 0.0)
            peak_nav = max(peak_nav, nav)
            drawdown = (nav - peak_nav) / peak_nav if peak_nav > 0 else 0.0
            drawdown = _to_float(drawdown, 0.0)

            nav_row = {
                "run_id": run_id,
                "trade_date": next_trade_date,
                "nav": nav,
                "cash": portfolio.cash,
                "position_value": total_equity_t1 - portfolio.cash,
                "daily_return": None,
                "cum_return": nav - 1.0,
                "drawdown": drawdown,
                "exposure": (total_equity_t1 - portfolio.cash) / total_equity_t1 if total_equity_t1 > 0 else 0.0,
                "benchmark_nav": None,
            }
            upsert_backtest_nav([nav_row])
            nav_rows.append(nav_row)

            score_map_for_snapshot = {str(row.get("ts_code")): _to_float(row.get("score")) for row in scored.to_dict(orient="records")}
            position_rows = portfolio.to_positions_snapshot(
                run_id=run_id,
                trade_date=next_trade_date,
                close_map=close_map_t1,
                score_map=score_map_for_snapshot,
                trade_index_map=trade_index_map,
            )
            if position_rows:
                upsert_backtest_positions(position_rows)

            signal_records = list(signal_rows.values())
            if signal_store_topk > 0 and len(signal_records) > signal_store_topk:
                signal_records = sorted(
                    signal_records,
                    key=lambda item: (
                        -_to_float(item.get("score"), 0.0),
                        str(item.get("ts_code") or ""),
                    ),
                )[:signal_store_topk]
            if signal_records:
                upsert_backtest_signals(signal_records)

            logger.info(
                "[%s/%s] signal_date=%s exec_date=%s direction=%s orders=%s trades=%s nav=%.4f cash=%.2f positions=%s",
                idx,
                len(open_dates) - 1,
                trade_date,
                next_trade_date,
                score_direction,
                len(orders),
                len(trades),
                nav,
                portfolio.cash,
                portfolio.holding_count(),
            )

        summary_metrics = build_summary_metrics(
            nav_rows=nav_rows,
            initial_capital=initial_capital,
            trades=all_trades,
        )
        update_backtest_run(
            run_id=run_id,
            status="success",
            summary_metrics=summary_metrics,
            error_message="",
            finished_at=dt.datetime.now(dt.UTC),
        )
        return summary_metrics


def run_backtest_with_guard(strategy: StrategyProtocol, config: BacktestRunConfig) -> dict[str, Any]:
    engine = BacktestEngine(strategy=strategy)
    try:
        return engine.run(config)
    except Exception as exc:
        update_backtest_run(
            run_id=config.run_id,
            status="failed",
            error_message=str(exc),
            finished_at=dt.datetime.now(dt.UTC),
        )
        raise
