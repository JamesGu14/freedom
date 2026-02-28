from __future__ import annotations

import datetime as dt
import logging
from typing import Any

import pandas as pd

from app.data.duckdb_backtest_store import list_stock_universe, normalize_date
from app.data.mongo import get_collection
from app.data.mongo_strategy_signal import (
    delete_strategy_signals,
    get_latest_signal_date,
    list_strategy_signals,
    upsert_strategy_signals,
)
from app.quant.allocator import calc_target_amount, calc_target_weight
from app.quant.params_registry import validate_and_normalize_params
from app.quant.base import StrategyContext
from app.quant.context import load_daily_data_bundle
from app.quant.engine import (
    _calc_list_days,
    _effective_score,
    _infer_board,
    _normalize_allowed_boards,
    _normalize_index_code,
    _normalize_score_direction,
    _normalize_sector_source_weights,
    _load_index_member_codes,
    _resolve_sector_strength,
    _to_bool,
    _to_float,
)
from app.quant.factors_market import classify_market_regime
from app.quant.factors_sector import build_sector_strength_maps
from app.quant.registry import load_strategy

STRATEGY_PORTFOLIO_ID = "__strategy__"
logger = logging.getLogger(__name__)


def is_open_trade_date(trade_date: str, exchange: str = "SSE") -> bool:
    row = get_collection("trade_calendar").find_one(
        {"exchange": exchange, "cal_date": trade_date},
        {"_id": 0, "is_open": 1},
    )
    return bool(row and str(row.get("is_open")) == "1")


def get_next_open_trade_date(trade_date: str, exchange: str = "SSE") -> str | None:
    row = get_collection("trade_calendar").find_one(
        {
            "exchange": exchange,
            "cal_date": {"$gt": trade_date},
            "is_open": {"$in": ["1", 1]},
        },
        {"_id": 0, "cal_date": 1},
        sort=[("cal_date", 1)],
    )
    if not row:
        return None
    value = str(row.get("cal_date") or "").strip()
    return value or None


def list_strategy_signal_dates(
    *,
    strategy_version_id: str | None = None,
    portfolio_id: str | None = STRATEGY_PORTFOLIO_ID,
    limit: int = 120,
) -> list[str]:
    query: dict[str, Any] = {}
    if strategy_version_id:
        query["strategy_version_id"] = strategy_version_id
    if portfolio_id:
        query["portfolio_id"] = portfolio_id
    dates = get_collection("strategy_signals_daily").distinct("signal_date", query)
    items = sorted([str(item) for item in dates if item], reverse=True)
    if limit > 0:
        return items[:limit]
    return items


def query_strategy_signals(
    *,
    signal_date: str | None = None,
    strategy_version_id: str | None = None,
    portfolio_id: str | None = None,
    portfolio_type: str | None = None,
    signal: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict[str, Any]], int]:
    return list_strategy_signals(
        signal_date=signal_date,
        strategy_version_id=strategy_version_id,
        portfolio_id=portfolio_id,
        portfolio_type=portfolio_type,
        signal=signal,
        page=page,
        page_size=page_size,
    )


def query_latest_signal_date(
    *,
    strategy_version_id: str | None = None,
    portfolio_id: str | None = STRATEGY_PORTFOLIO_ID,
    portfolio_type: str | None = "strategy",
) -> str | None:
    return get_latest_signal_date(
        strategy_version_id=strategy_version_id,
        portfolio_id=portfolio_id,
        portfolio_type=portfolio_type,
    )


def _active_strategy_ids() -> set[str]:
    cursor = get_collection("strategy_definitions").find(
        {"status": "active"},
        {"_id": 0, "strategy_id": 1},
    )
    return {str(item.get("strategy_id") or "").strip() for item in cursor if item.get("strategy_id")}


def _load_strategy_versions(
    *,
    strategy_id: str | None = None,
    strategy_version_id: str | None = None,
) -> list[dict[str, Any]]:
    query: dict[str, Any] = {}
    if strategy_id:
        query["strategy_id"] = strategy_id
    if strategy_version_id:
        query["strategy_version_id"] = strategy_version_id
    items = list(
        get_collection("strategy_versions")
        .find(query, {"_id": 0})
        .sort([("strategy_id", 1), ("created_at", -1)])
    )
    if strategy_version_id:
        return items
    active_ids = _active_strategy_ids()
    return [item for item in items if str(item.get("strategy_id") or "") in active_ids]


def _filter_frame(frame: pd.DataFrame, *, signal_date: str, params: dict[str, Any]) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame()
    data = frame.copy()
    allowed_boards = _normalize_allowed_boards(params.get("allowed_boards"))
    data["board"] = data["ts_code"].map(_infer_board)
    data = data[data["board"].isin(allowed_boards)]
    data["list_days"] = data.apply(
        lambda row: _calc_list_days(signal_date, str(row.get("list_date") or "")),
        axis=1,
    )
    data = data[data["list_days"] >= 120]
    data = data[data["amount"].fillna(0) >= _to_float(params.get("min_avg_amount_20d"), 25_000.0)]
    data = data[data["close"].notna() & data["open"].notna()]
    return data


def _apply_universe_index_filter(frame: pd.DataFrame, *, signal_date: str, params: dict[str, Any]) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame()
    index_code = _normalize_index_code(params.get("universe_index_code"))
    if not index_code:
        return frame
    member_codes = _load_index_member_codes(index_code=index_code, start_date=signal_date, end_date=signal_date)
    if not member_codes:
        logger.warning("signal universe filter skipped: index=%s has no members on %s", index_code, signal_date)
        return frame
    return frame[frame["ts_code"].isin(member_codes)].copy()


def _resolve_market_context(
    *,
    market_factor_t: dict[str, Any] | None,
    params: dict[str, Any],
) -> tuple[str, float]:
    market_regime, exposure_default = classify_market_regime(
        market_factor_t or {},
        recent_pct_changes=[],
    )
    exposure_map = dict(params.get("market_exposure") or {})
    market_exposure = _to_float(exposure_map.get(market_regime), exposure_default)
    exposure_floor = max(min(_to_float(params.get("market_exposure_floor"), 0.4), 1.0), 0.0)
    if market_exposure < exposure_floor:
        market_exposure = exposure_floor
    return market_regime, market_exposure


def _build_signal_rows(
    *,
    signal_date: str,
    signal_trade_date: str,
    strategy_id: str,
    strategy_version_id: str,
    params: dict[str, Any],
    scored: pd.DataFrame,
    market_regime: str,
    market_exposure: float,
    portfolio_id: str,
    portfolio_type: str,
) -> list[dict[str, Any]]:
    if scored.empty:
        return []
    buy_threshold = _to_float(params.get("buy_threshold"), 75.0)
    sell_threshold = _to_float(params.get("sell_threshold"), 50.0)
    signal_store_topk = int(params.get("signal_store_topk", 100) or 0)
    if signal_store_topk > 0:
        scored = scored.head(signal_store_topk)

    slot_weight = _to_float(params.get("slot_weight"), 0.20)
    score_ceiling = _to_float(params.get("score_ceiling"), 100.0)
    slot_min_scale = _to_float(params.get("slot_min_scale"), 0.6)
    sector_cap = _to_float(params.get("sector_max"), 0.40)
    signal_capital = _to_float(params.get("signal_capital"), 1_000_000.0)

    now = dt.datetime.now(dt.UTC)
    rows: list[dict[str, Any]] = []
    for rank, item in enumerate(scored.to_dict(orient="records"), start=1):
        score = _to_float(item.get("score"), 0.0)
        raw_score = _to_float(item.get("raw_score"), 0.0)
        signal = "HOLD"
        reason_codes = ["score_between_thresholds"]
        target_weight = 0.0
        target_amount = 0.0
        if score >= buy_threshold:
            signal = "BUY"
            reason_codes = ["score_gte_buy_threshold"]
            if (
                _to_float(item.get("macd_hist"), 0.0) > 0
                and _to_float(item.get("macd"), 0.0) < 0
                and _to_float(item.get("macd_signal"), 0.0) < 0
            ):
                reason_codes.append("macd_zero_axis_golden_cross")
            target_weight = calc_target_weight(
                score=score,
                market_exposure=market_exposure,
                slot_weight=slot_weight,
                buy_threshold=buy_threshold,
                score_ceiling=score_ceiling,
                slot_min_scale=slot_min_scale,
                sector_weight=1.0,
            )
            target_weight = min(max(target_weight, 0.0), max(sector_cap, 0.0))
            target_amount = calc_target_amount(
                total_equity=signal_capital,
                target_weight=target_weight,
            )
        elif score <= sell_threshold:
            signal = "SELL"
            reason_codes = ["score_lte_sell_threshold"]

        rows.append(
            {
                "signal_date": signal_date,
                "signal_trade_date": signal_trade_date,
                "strategy_id": strategy_id,
                "strategy_version_id": strategy_version_id,
                "portfolio_id": portfolio_id,
                "portfolio_type": portfolio_type,
                "ts_code": str(item.get("ts_code") or "").strip().upper(),
                "stock_name": str(item.get("name") or "").strip(),
                "industry": str(item.get("industry") or "").strip(),
                "signal": signal,
                "score": score,
                "raw_score": raw_score,
                "rank": rank,
                "target_weight": target_weight,
                "target_amount": target_amount,
                "reason_codes": reason_codes,
                "market_regime": market_regime,
                "generated_at": now,
            }
        )
    return rows


def generate_strategy_signals_for_date(
    *,
    signal_date: str,
    strategy_id: str | None = None,
    strategy_version_id: str | None = None,
    portfolio_id: str = STRATEGY_PORTFOLIO_ID,
    portfolio_type: str = "strategy",
) -> dict[str, Any]:
    signal_date = normalize_date(signal_date)
    if not is_open_trade_date(signal_date):
        return {
            "signal_date": signal_date,
            "status": "skipped",
            "reason": "non_trading_day",
            "version_stats": [],
            "total_upserted": 0,
        }
    signal_trade_date = get_next_open_trade_date(signal_date)
    if not signal_trade_date:
        return {
            "signal_date": signal_date,
            "status": "skipped",
            "reason": "next_trading_day_not_found",
            "version_stats": [],
            "total_upserted": 0,
        }

    versions = _load_strategy_versions(
        strategy_id=strategy_id,
        strategy_version_id=strategy_version_id,
    )
    if not versions:
        return {
            "signal_date": signal_date,
            "status": "skipped",
            "reason": "no_target_strategy_versions",
            "version_stats": [],
            "total_upserted": 0,
        }

    universe_df = list_stock_universe()
    bundle = load_daily_data_bundle(
        trade_date=signal_date,
        next_trade_date=signal_trade_date,
        universe_df=universe_df,
    )
    if bundle.frame_t.empty:
        return {
            "signal_date": signal_date,
            "status": "degraded",
            "reason": "frame_t_empty",
            "version_stats": [],
            "total_upserted": 0,
        }

    sector_strength_maps = build_sector_strength_maps(bundle.sector_rows_t)
    sector_strength_name_map = sector_strength_maps.get("name", {})
    sector_strength_sw_map = sector_strength_maps.get("sw_code", {})
    sector_strength_ci_map = sector_strength_maps.get("ci_code", {})
    shenwan_member_codes_map = bundle.shenwan_member_codes_t or {}
    citic_member_codes_map = bundle.citic_member_codes_t or {}

    version_stats: list[dict[str, Any]] = []
    total_upserted = 0
    for version in versions:
        strategy_id_value = str(version.get("strategy_id") or "").strip()
        strategy_version_id_value = str(version.get("strategy_version_id") or "").strip()
        strategy_key = str(version.get("strategy_key") or "").strip() or str((version.get("params_snapshot") or {}).get("strategy_key") or "multifactor_v1")
        params, _ = validate_and_normalize_params(strategy_key, dict(version.get("params_snapshot") or {}))
        market_regime, market_exposure = _resolve_market_context(
            market_factor_t=bundle.market_factor_t,
            params=params,
        )

        frame = _apply_universe_index_filter(bundle.frame_t, signal_date=signal_date, params=params)
        frame = _filter_frame(frame, signal_date=signal_date, params=params)
        if frame.empty:
            removed = delete_strategy_signals(
                signal_date=signal_date,
                strategy_version_id=strategy_version_id_value,
                portfolio_id=portfolio_id,
            )
            version_stats.append(
                {
                    "strategy_version_id": strategy_version_id_value,
                    "status": "skipped",
                    "reason": "no_candidates_after_filters",
                    "removed": removed,
                    "upserted": 0,
                }
            )
            continue

        use_member_sector_mapping = _to_bool(params.get("use_member_sector_mapping"), True)
        sector_source_weights = _normalize_sector_source_weights(params.get("sector_source_weights"))
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

        strategy = load_strategy(strategy_key)
        strategy_context = StrategyContext(
            trade_date=signal_date,
            frame=frame,
            market_regime=market_regime,
            market_exposure=market_exposure,
            params=params,
        )
        scored = strategy.score(strategy_context)
        if scored is None or scored.empty:
            removed = delete_strategy_signals(
                signal_date=signal_date,
                strategy_version_id=strategy_version_id_value,
                portfolio_id=portfolio_id,
            )
            version_stats.append(
                {
                    "strategy_version_id": strategy_version_id_value,
                    "status": "skipped",
                    "reason": "score_empty",
                    "removed": removed,
                    "upserted": 0,
                }
            )
            continue

        score_direction = _normalize_score_direction(params.get("score_direction"))
        scored["raw_score"] = pd.to_numeric(scored.get("total_score"), errors="coerce").fillna(0.0)
        scored["score"] = scored["raw_score"].apply(lambda x: _effective_score(x, score_direction))
        scored = scored.sort_values(by=["score", "sector_strength", "ts_code"], ascending=[False, False, True])

        rows = _build_signal_rows(
            signal_date=signal_date,
            signal_trade_date=signal_trade_date,
            strategy_id=strategy_id_value,
            strategy_version_id=strategy_version_id_value,
            params=params,
            scored=scored,
            market_regime=market_regime,
            market_exposure=market_exposure,
            portfolio_id=portfolio_id,
            portfolio_type=portfolio_type,
        )

        removed = delete_strategy_signals(
            signal_date=signal_date,
            strategy_version_id=strategy_version_id_value,
            portfolio_id=portfolio_id,
        )
        upserted = upsert_strategy_signals(rows)
        total_upserted += upserted
        version_stats.append(
            {
                "strategy_version_id": strategy_version_id_value,
                "status": "success",
                "reason": "",
                "removed": removed,
                "upserted": upserted,
                "strategy_key": strategy_key,
                "market_regime": market_regime,
            }
        )

    return {
        "signal_date": signal_date,
        "signal_trade_date": signal_trade_date,
        "status": "success",
        "reason": "",
        "version_stats": version_stats,
        "total_upserted": total_upserted,
    }
