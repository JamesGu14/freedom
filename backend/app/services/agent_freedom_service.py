from __future__ import annotations

import datetime as dt
import math
import uuid
from collections import defaultdict
from types import SimpleNamespace
from typing import Any

from app.data.duckdb_store import list_latest_daily_prices
from app.data.mongo import get_collection
from app.data.mongo_agent_freedom import (
    STRATEGY_PORTFOLIO_ID,
    ensure_agent_freedom_indexes,
    get_agent_report_daily,
    list_agent_job_runs,
    list_portfolio_positions,
    list_skill_call_logs,
    list_strategy_signals_for_date,
    replace_portfolio_snapshot,
    replace_industry_rotation_daily,
    replace_risk_control_daily,
    upsert_agent_report_daily,
    upsert_ai_signal_staging,
    upsert_market_regime_daily,
    upsert_portfolio_account,
    upsert_portfolio_positions,
    upsert_skill_call_log,
    upsert_strategy_signal_updates,
)
from app.data.mongo_strategy_job_run import finish_strategy_job_run, start_strategy_job_run
from app.data.mongo_trade_calendar import is_trading_day
from app.quant.factors_market import classify_market_regime
from app.services.ai_runner_client import call_skill
from app.services.report_service import build_daily_report_markdown, push_feishu_text
from app.services.strategy_signal_service import generate_strategy_signals_for_date


_SKILL_P0 = [
    "findata-toolkit-cn",
    "quant-factor-screener",
    "sector-rotation-detector",
]

_POSITION_LIMIT_DEFAULT = 0.08
_POSITION_LIMIT_ATTACK = 0.10
_INDUSTRY_LIMIT = 0.25
_TOP5_LIMIT = 0.45
_TOP10_LIMIT = 0.70
_MAX_HOLDINGS = 50
_MIN_HOLDINGS = 15
_DRAWDOWN_L1 = 0.05
_DRAWDOWN_L2 = 0.08
_DRAWDOWN_L3 = 0.12


def _normalize_date(value: str | None) -> str:
    if not value:
        return dt.datetime.now().strftime("%Y%m%d")
    text = str(value).strip().replace("-", "")
    if len(text) != 8 or not text.isdigit():
        raise ValueError("invalid trade_date, use YYYYMMDD or YYYY-MM-DD")
    return text


def _to_float(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_ts_code(value: Any) -> str:
    text = str(value or "").strip().upper()
    if not text:
        return ""
    if "." in text:
        return text
    if len(text) == 6 and text.isdigit():
        if text.startswith(("600", "601", "603", "605", "688", "689", "900")):
            return f"{text}.SH"
        if text.startswith(("000", "001", "002", "003", "200", "300", "301")):
            return f"{text}.SZ"
        if text.startswith(("4", "8")):
            return f"{text}.BJ"
    return text


def _safe_div(a: float, b: float) -> float:
    if abs(b) < 1e-9:
        return 0.0
    return a / b


def _score_from_rank(rank: Any, rank_total: Any) -> float:
    rank_value = _to_float(rank, default=0.0)
    total_value = _to_float(rank_total, default=0.0)
    if total_value <= 1:
        return 50.0
    pct = 1.0 - _safe_div(rank_value - 1.0, total_value - 1.0)
    return max(min(pct * 100.0, 100.0), 0.0)


def _score_from_pct_change(value: Any) -> float:
    pct = _to_float(value, default=0.0)
    normalized = (pct + 5.0) / 10.0
    return max(min(normalized, 1.0), 0.0) * 100.0


def _latest_market_factor_row(trade_date: str) -> dict[str, Any] | None:
    query = {
        "source": "market",
        "ts_code": "000300.SH",
        "trade_date": {"$lte": trade_date},
    }
    row = get_collection("index_factor_pro").find_one(
        query,
        {"_id": 0},
        sort=[("trade_date", -1)],
    )
    if row:
        return row

    return get_collection("index_factor_pro").find_one(
        {"source": "market", "trade_date": {"$lte": trade_date}},
        {"_id": 0},
        sort=[("trade_date", -1)],
    )


def _recent_market_pct_changes(trade_date: str, limit: int = 20) -> list[float]:
    cursor = (
        get_collection("index_factor_pro")
        .find(
            {
                "source": "market",
                "ts_code": "000300.SH",
                "trade_date": {"$lte": trade_date},
            },
            {"_id": 0, "pct_change": 1},
        )
        .sort([("trade_date", -1)])
        .limit(max(limit, 1))
    )
    rows = list(cursor)
    rows.reverse()
    return [_to_float(item.get("pct_change"), default=0.0) for item in rows]


def _latest_shenwan_rows(trade_date: str) -> list[dict[str, Any]]:
    latest = get_collection("shenwan_daily").find_one(
        {"trade_date": {"$lte": trade_date}},
        {"_id": 0, "trade_date": 1},
        sort=[("trade_date", -1)],
    )
    if not latest:
        return []
    use_date = str(latest.get("trade_date") or "")
    if not use_date:
        return []
    cursor = get_collection("shenwan_daily").find(
        {"trade_date": use_date, "level": 1},
        {"_id": 0},
    )
    return list(cursor)


def _fallback_signal_rows(trade_date: str, strategy_version_id: str | None = None) -> tuple[list[dict[str, Any]], str | None]:
    query: dict[str, Any] = {
        "portfolio_id": STRATEGY_PORTFOLIO_ID,
        "portfolio_type": "strategy",
        "signal_date": {"$lte": trade_date},
    }
    if strategy_version_id:
        query["strategy_version_id"] = strategy_version_id
    latest = get_collection("strategy_signals_daily").find_one(
        query,
        {"_id": 0, "signal_date": 1},
        sort=[("signal_date", -1)],
    )
    if not latest:
        return [], None
    fallback_date = str(latest.get("signal_date") or "").strip()
    if not fallback_date:
        return [], None
    rows = list_strategy_signals_for_date(
        signal_date=fallback_date,
        strategy_version_id=strategy_version_id,
    )
    return rows, fallback_date


def _compute_data_quality(trade_date: str) -> dict[str, Any]:
    cursor = (
        get_collection("data_sync_job_runs")
        .find({}, {"_id": 0, "status": 1, "created_at": 1, "job_id": 1})
        .sort([("created_at", -1)])
        .limit(20)
    )
    rows = list(cursor)
    if not rows:
        return {
            "ok": False,
            "status": "degraded",
            "reason": "data_sync_job_runs_empty",
            "failed_ratio": 1.0,
            "trade_date": trade_date,
        }

    bad = 0
    for row in rows:
        status = str(row.get("status") or "").lower()
        if status not in {"success", "finished", "done", "completed", "running"}:
            bad += 1
    failed_ratio = _safe_div(float(bad), float(len(rows)))
    return {
        "ok": failed_ratio <= 0.05,
        "status": "ok" if failed_ratio <= 0.05 else "degraded",
        "reason": "",
        "failed_ratio": failed_ratio,
        "trade_date": trade_date,
        "sample_size": len(rows),
    }


def _log_skill_result(
    *,
    trade_date: str,
    skill_name: str,
    result: Any,
    input_payload: dict[str, Any],
) -> None:
    record = {
        "request_id": result.request_id,
        "trade_date": trade_date,
        "skill_name": skill_name,
        "status": result.status,
        "ok": result.ok,
        "latency_ms": result.latency_ms,
        "attempts": result.attempts,
        "error": result.error,
        "model": result.model,
        "input": input_payload,
        "output": result.data if result.ok else None,
    }
    upsert_skill_call_log(record)


def _call_p0_skills(
    *,
    trade_date: str,
    market_row: dict[str, Any] | None,
    signal_rows: list[dict[str, Any]],
    shenwan_rows: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[str], list[str]]:
    results: dict[str, Any] = {}
    degrade_flags: list[str] = []
    explain_refs: list[str] = []

    skill_inputs: dict[str, dict[str, Any]] = {
        "findata-toolkit-cn": {
            "market": market_row or {},
            "trade_date": trade_date,
        },
        "quant-factor-screener": {
            "trade_date": trade_date,
            "stocks": [
                {
                    "ts_code": item.get("ts_code"),
                    "industry": item.get("industry"),
                    "score": item.get("score"),
                }
                for item in signal_rows[:300]
            ],
        },
        "sector-rotation-detector": {
            "trade_date": trade_date,
            "industries": [
                {
                    "industry_code": item.get("ts_code"),
                    "industry_name": item.get("name"),
                    "pct_change": item.get("pct_change"),
                    "rank": item.get("rank"),
                    "rank_total": item.get("rank_total"),
                }
                for item in shenwan_rows
            ],
        },
    }

    for skill_name in _SKILL_P0:
        req_id = uuid.uuid4().hex
        try:
            result = call_skill(
                skill_name=skill_name,
                trade_date=trade_date,
                request_id=req_id,
                input_payload=skill_inputs.get(skill_name, {}),
            )
        except Exception as exc:  # graceful degrade when runner is unavailable
            result = SimpleNamespace(
                request_id=req_id,
                skill_name=skill_name,
                ok=False,
                status="upstream_error",
                data=None,
                error=str(exc),
                latency_ms=0,
                attempts=1,
                model="",
            )
        _log_skill_result(
            trade_date=trade_date,
            skill_name=skill_name,
            result=result,
            input_payload=skill_inputs.get(skill_name, {}),
        )
        explain_refs.append(req_id)
        if not result.ok:
            degrade_flags.append(f"{skill_name}:{result.status}")
            continue
        results[skill_name] = result.data or {}

    return results, degrade_flags, explain_refs


def _resolve_regime(
    *,
    trade_date: str,
    market_row: dict[str, Any] | None,
    findata_payload: dict[str, Any] | None,
) -> tuple[dict[str, Any], str, float]:
    recent_pct = _recent_market_pct_changes(trade_date=trade_date, limit=20)
    local_regime, local_exposure = classify_market_regime(market_row or {}, recent_pct_changes=recent_pct)

    macro_score = _to_float((findata_payload or {}).get("macro_score"), default=50.0)
    northbound_score = _to_float((findata_payload or {}).get("northbound_score"), default=50.0)
    risk_hint = str((findata_payload or {}).get("risk_hint") or "").strip()

    regime = local_regime
    if macro_score <= 40 and northbound_score <= 40:
        regime = "risk_off"
    elif macro_score >= 60 and northbound_score >= 60:
        regime = "risk_on"

    exposure_map = {
        "risk_on": 1.0,
        "neutral": 0.7,
        "risk_off": 0.4,
    }
    exposure = float(exposure_map.get(regime, local_exposure))
    reason = f"local={local_regime}, macro_score={macro_score:.1f}, northbound_score={northbound_score:.1f}, hint={risk_hint or '-'}"

    record = {
        "trade_date": trade_date,
        "regime": regime,
        "market_exposure": exposure,
        "reason": reason,
        "local_regime": local_regime,
        "local_exposure": local_exposure,
        "macro_score": macro_score,
        "northbound_score": northbound_score,
        "risk_hint": risk_hint,
        "market_row": market_row or {},
    }
    return record, regime, exposure


def _build_industry_rotation_rows(
    *,
    trade_date: str,
    shenwan_rows: list[dict[str, Any]],
    sector_payload: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    ai_rows = (sector_payload or {}).get("rows")
    ai_map: dict[str, dict[str, Any]] = {}
    if isinstance(ai_rows, list):
        for item in ai_rows:
            if not isinstance(item, dict):
                continue
            code = str(item.get("industry_code") or "").strip().upper()
            if not code:
                continue
            ai_map[code] = item

    rows: list[dict[str, Any]] = []
    for item in shenwan_rows:
        industry_code = str(item.get("ts_code") or "").strip().upper()
        if not industry_code:
            continue
        local_score = _score_from_rank(item.get("rank"), item.get("rank_total")) * 0.7 + _score_from_pct_change(item.get("pct_change")) * 0.3
        ai_item = ai_map.get(industry_code)
        ai_score = _to_float(ai_item.get("score"), default=local_score) if ai_item else local_score
        final_score = local_score * 0.7 + ai_score * 0.3 if ai_item else local_score
        rows.append(
            {
                "trade_date": trade_date,
                "industry_code": industry_code,
                "industry_name": str(item.get("name") or "").strip() or industry_code,
                "score": round(final_score, 4),
                "score_local": round(local_score, 4),
                "score_ai": round(ai_score, 4),
                "pct_change": _to_float(item.get("pct_change")),
                "rank": _to_float(item.get("rank")),
                "rank_total": _to_float(item.get("rank_total")),
                "ai_bias": str(ai_item.get("bias") or "") if ai_item else "",
            }
        )

    if not rows:
        return rows

    rows.sort(key=lambda x: float(x.get("score") or 0), reverse=True)
    n = len(rows)
    top_cut = max(int(math.ceil(n * 0.2)), 1)
    bottom_cut = max(int(math.ceil(n * 0.2)), 1)
    for idx, row in enumerate(rows):
        if idx < top_cut:
            row["allocation_tag"] = "overweight"
        elif idx >= n - bottom_cut:
            row["allocation_tag"] = "underweight"
        else:
            row["allocation_tag"] = "neutral"
    return rows


def _normalize_position_type(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return "balanced"
    if text in {"attack", "aggressive", "risk_on", "offense"}:
        return "attack"
    if text in {"defensive", "defense", "risk_off"}:
        return "defensive"
    if text in {"balanced", "stable", "neutral"}:
        return "balanced"
    if "进攻" in text:
        return "attack"
    if "防守" in text:
        return "defensive"
    if "稳健" in text:
        return "balanced"
    return "balanced"


def _to_trade_date_text(value: Any) -> str:
    if isinstance(value, dt.datetime):
        return value.strftime("%Y%m%d")
    if isinstance(value, dt.date):
        return value.strftime("%Y%m%d")
    text = str(value or "").strip().replace("-", "")
    if len(text) == 8 and text.isdigit():
        return text
    return ""


def _calc_holding_days(*, entry_date: Any, trade_date: str) -> int | None:
    entry_text = _to_trade_date_text(entry_date)
    if not entry_text:
        return None
    try:
        entry = dt.datetime.strptime(entry_text, "%Y%m%d").date()
        current = dt.datetime.strptime(trade_date, "%Y%m%d").date()
    except ValueError:
        return None
    days = (current - entry).days
    if days < 0:
        return None
    return days


def _append_reason_codes(row: dict[str, Any], reason_code: str) -> None:
    codes = row.get("reason_codes")
    if not isinstance(codes, list):
        codes = []
    reason = str(reason_code or "").strip()
    if reason and reason not in codes:
        codes.append(reason)
    row["reason_codes"] = codes


def _ensure_sell_signal(
    *,
    ts_code: str,
    updated_rows: list[dict[str, Any]],
    updated_map: dict[str, dict[str, Any]],
    default_strategy_version_id: str,
    trade_date: str,
    regime: str,
    position: dict[str, Any] | None,
    reason_code: str,
) -> None:
    code = str(ts_code or "").strip().upper()
    if not code:
        return
    row = updated_map.get(code)
    if row is None:
        strategy_version_id = str((position or {}).get("strategy_version_id") or "").strip() or default_strategy_version_id
        if not strategy_version_id:
            return
        row = {
            "signal_date": trade_date,
            "signal_trade_date": trade_date,
            "ts_code": code,
            "stock_name": str((position or {}).get("stock_name") or (position or {}).get("name") or "").strip(),
            "industry": str((position or {}).get("industry") or "").strip(),
            "signal": "SELL",
            "score": -1.0,
            "raw_score": -1.0,
            "rank": 9999,
            "target_weight": 0.0,
            "target_amount": 0.0,
            "reason_codes": [],
            "market_regime": regime,
            "generated_at": dt.datetime.now(dt.UTC),
            "strategy_id": str((position or {}).get("strategy_id") or "").strip(),
            "strategy_version_id": strategy_version_id,
            "portfolio_id": STRATEGY_PORTFOLIO_ID,
            "portfolio_type": "strategy",
            "signal_source": "risk_engine",
            "degrade_flags": [],
            "explain_refs": [],
            "risk_override": True,
        }
        updated_rows.append(row)
        updated_map[code] = row
    row["signal"] = "SELL"
    row["target_weight"] = 0.0
    row["target_amount"] = 0.0
    row["risk_override"] = True
    _append_reason_codes(row, reason_code)


def _normalize_signal_ranks(rows: list[dict[str, Any]]) -> None:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("strategy_version_id") or "")].append(row)
    for _, items in grouped.items():
        items.sort(key=lambda x: (_to_float(x.get("score"), 0.0), str(x.get("ts_code") or "")), reverse=True)
        for rank, row in enumerate(items, start=1):
            row["rank"] = rank


def _calc_drawdown_20d(*, account_id: str, trade_date: str, current_equity: float) -> tuple[float, int]:
    pipeline = [
        {
            "$match": {
                "account_id": account_id,
                "trade_date": {"$lte": trade_date},
            }
        },
        {
            "$project": {
                "trade_date": 1,
                "equity_proxy": {
                    "$ifNull": [
                        "$market_value",
                        {"$ifNull": ["$position_value", {"$ifNull": ["$value", {"$ifNull": ["$amount", 0]}]}]},
                    ]
                },
            }
        },
        {"$group": {"_id": "$trade_date", "equity": {"$sum": "$equity_proxy"}}},
        {"$sort": {"_id": -1}},
        {"$limit": 20},
    ]
    rows = list(get_collection("portfolio_snapshots").aggregate(pipeline))
    series: list[tuple[str, float]] = []
    for item in rows:
        date_text = _to_trade_date_text(item.get("_id"))
        equity = _to_float(item.get("equity"), default=0.0)
        if not date_text or equity <= 0:
            continue
        series.append((date_text, equity))

    if current_equity > 0:
        current_exists = any(date_text == trade_date for date_text, _ in series)
        if not current_exists:
            series.append((trade_date, current_equity))

    if len(series) < 2:
        return 0.0, len(series)

    series.sort(key=lambda x: x[0])
    values = [item[1] for item in series[-20:] if item[1] > 0]
    if len(values) < 2:
        return 0.0, len(values)
    peak = max(values)
    if peak <= 0:
        return 0.0, len(values)
    current = values[-1]
    drawdown = max(peak - current, 0.0) / peak
    return drawdown, len(values)


def _apply_risk_controls_v1(
    *,
    trade_date: str,
    account_id: str,
    regime: str,
    updated_signals: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    risk_rows: list[dict[str, Any]] = []
    risk_seen: set[tuple[str, str, str]] = set()

    updated_map: dict[str, dict[str, Any]] = {}
    default_strategy_version_id = ""
    for row in updated_signals:
        code = str(row.get("ts_code") or "").strip().upper()
        if code:
            updated_map[code] = row
        if not default_strategy_version_id:
            default_strategy_version_id = str(row.get("strategy_version_id") or "").strip()

    def add_risk(ts_code: str, rule_code: str, action: str, detail: str) -> None:
        key = (str(ts_code or "").strip().upper(), str(rule_code or "").strip(), str(action or "").strip())
        if key in risk_seen:
            return
        risk_seen.add(key)
        risk_rows.append(
            {
                "trade_date": trade_date,
                "account_id": account_id,
                "ts_code": key[0] or "__portfolio__",
                "rule_code": key[1],
                "action": key[2],
                "detail": detail,
            }
        )

    positions_raw = list_portfolio_positions(account_id)
    if not positions_raw:
        return updated_signals, risk_rows, {"position_count": 0, "drawdown_20d": 0.0, "drawdown_days": 0}

    position_codes = [str(item.get("ts_code") or "").strip().upper() for item in positions_raw if item.get("ts_code")]
    latest_prices = list_latest_daily_prices(position_codes)
    account_doc = get_collection("portfolio_accounts").find_one({"account_id": account_id}, {"_id": 0}) or {}

    positions: list[dict[str, Any]] = []
    for raw in positions_raw:
        ts_code = str(raw.get("ts_code") or "").strip().upper()
        if not ts_code:
            continue
        qty = _to_float(raw.get("quantity"), default=_to_float(raw.get("shares"), default=_to_float(raw.get("qty"), default=0.0)))
        cost_price = _to_float(raw.get("cost_price"), default=_to_float(raw.get("avg_cost"), default=_to_float(raw.get("cost"), default=0.0)))
        market_price = _to_float(
            raw.get("current_price"),
            default=_to_float(raw.get("market_price"), default=_to_float((latest_prices.get(ts_code) or {}).get("close"), default=0.0)),
        )
        market_value = _to_float(
            raw.get("market_value"),
            default=_to_float(raw.get("position_value"), default=_to_float(raw.get("value"), default=_to_float(raw.get("amount"), default=0.0))),
        )
        if market_value <= 0 and qty > 0 and market_price > 0:
            market_value = qty * market_price

        pnl_ratio: float | None = None
        if cost_price > 0 and market_price > 0:
            pnl_ratio = _safe_div(market_price - cost_price, cost_price)
        else:
            cost_value = _to_float(raw.get("cost_value"), default=_to_float(raw.get("cost_amount"), default=0.0))
            if cost_value > 0 and market_value > 0:
                pnl_ratio = _safe_div(market_value - cost_value, cost_value)

        holding_days = _calc_holding_days(
            entry_date=raw.get("entry_date") or raw.get("open_date") or raw.get("first_buy_date"),
            trade_date=trade_date,
        )
        if holding_days is None:
            holding_days = int(_to_float(raw.get("holding_days"), default=-1))
            if holding_days < 0:
                holding_days = None

        positions.append(
            {
                "ts_code": ts_code,
                "stock_name": str(raw.get("stock_name") or raw.get("name") or "").strip(),
                "industry": str(raw.get("industry") or (updated_map.get(ts_code) or {}).get("industry") or "").strip(),
                "position_type": _normalize_position_type(raw.get("position_type") or raw.get("bucket") or raw.get("style")),
                "strategy_version_id": str(raw.get("strategy_version_id") or "").strip(),
                "market_value": market_value,
                "market_price": market_price,
                "cost_price": cost_price,
                "pnl_ratio": pnl_ratio,
                "holding_days": holding_days,
            }
        )

    positions = [item for item in positions if item.get("market_value", 0.0) > 0]
    if not positions:
        return updated_signals, risk_rows, {"position_count": 0, "drawdown_20d": 0.0, "drawdown_days": 0}

    total_market_value = sum(_to_float(item.get("market_value"), default=0.0) for item in positions)
    account_total_equity = _to_float(account_doc.get("total_equity"), default=0.0)
    account_cash = _to_float(account_doc.get("cash"), default=0.0)
    total_equity = max(total_market_value + max(account_cash, 0.0), account_total_equity, total_market_value, 1.0)
    gross_exposure = _safe_div(total_market_value, total_equity)

    score_map = {str(row.get("ts_code") or "").strip().upper(): _to_float(row.get("score"), default=0.0) for row in updated_signals}
    for item in positions:
        item["weight"] = _safe_div(_to_float(item.get("market_value"), default=0.0), total_equity)
        item["score"] = score_map.get(str(item.get("ts_code") or "").strip().upper(), 0.0)

    stop_thresholds = {
        "attack": (-0.08, -0.12),
        "balanced": (-0.06, -0.10),
        "defensive": (-0.05, -0.08),
    }
    for item in positions:
        ts_code = str(item.get("ts_code") or "")
        pnl_ratio = item.get("pnl_ratio")
        if pnl_ratio is not None:
            stop_loss, force_loss = stop_thresholds.get(str(item.get("position_type") or "balanced"), (-0.06, -0.10))
            if pnl_ratio <= force_loss:
                add_risk(ts_code, "stop_loss_force", "force_sell", f"pnl={pnl_ratio:.2%}, threshold={force_loss:.2%}")
                _ensure_sell_signal(
                    ts_code=ts_code,
                    updated_rows=updated_signals,
                    updated_map=updated_map,
                    default_strategy_version_id=default_strategy_version_id,
                    trade_date=trade_date,
                    regime=regime,
                    position=item,
                    reason_code="stop_loss_force",
                )
            elif pnl_ratio <= stop_loss:
                add_risk(ts_code, "stop_loss_level2", "reduce_half", f"pnl={pnl_ratio:.2%}, threshold={stop_loss:.2%}")
                _ensure_sell_signal(
                    ts_code=ts_code,
                    updated_rows=updated_signals,
                    updated_map=updated_map,
                    default_strategy_version_id=default_strategy_version_id,
                    trade_date=trade_date,
                    regime=regime,
                    position=item,
                    reason_code="stop_loss_level2",
                )
            elif pnl_ratio <= -0.05:
                add_risk(ts_code, "stop_loss_warn", "watchlist", f"pnl={pnl_ratio:.2%}, threshold=-5.00%")

            holding_days = item.get("holding_days")
            if holding_days is not None and holding_days >= 30 and -0.02 <= pnl_ratio <= 0.02:
                add_risk(ts_code, "time_stop_loss", "rotate_out", f"holding_days={holding_days}, pnl={pnl_ratio:.2%}")
                _ensure_sell_signal(
                    ts_code=ts_code,
                    updated_rows=updated_signals,
                    updated_map=updated_map,
                    default_strategy_version_id=default_strategy_version_id,
                    trade_date=trade_date,
                    regime=regime,
                    position=item,
                    reason_code="time_stop_loss",
                )

        weight = _to_float(item.get("weight"), default=0.0)
        limit = _POSITION_LIMIT_ATTACK if str(item.get("position_type") or "") == "attack" else _POSITION_LIMIT_DEFAULT
        if weight > limit:
            add_risk(ts_code, "position_weight_cap", "reduce_position", f"weight={weight:.2%}, limit={limit:.2%}")
            _ensure_sell_signal(
                ts_code=ts_code,
                updated_rows=updated_signals,
                updated_map=updated_map,
                default_strategy_version_id=default_strategy_version_id,
                trade_date=trade_date,
                regime=regime,
                position=item,
                reason_code="position_weight_cap",
            )

    industry_map: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in positions:
        industry = str(item.get("industry") or "").strip()
        if industry:
            industry_map[industry].append(item)
    for industry, items in industry_map.items():
        total_weight = sum(_to_float(item.get("weight"), default=0.0) for item in items)
        if total_weight <= _INDUSTRY_LIMIT:
            continue
        need_reduce = total_weight - _INDUSTRY_LIMIT
        for candidate in sorted(items, key=lambda x: (_to_float(x.get("score"), 0.0), -_to_float(x.get("weight"), 0.0))):
            ts_code = str(candidate.get("ts_code") or "")
            add_risk(ts_code, "industry_cap", "reduce_industry", f"industry={industry}, weight={total_weight:.2%}, limit={_INDUSTRY_LIMIT:.2%}")
            _ensure_sell_signal(
                ts_code=ts_code,
                updated_rows=updated_signals,
                updated_map=updated_map,
                default_strategy_version_id=default_strategy_version_id,
                trade_date=trade_date,
                regime=regime,
                position=candidate,
                reason_code="industry_cap",
            )
            need_reduce -= _to_float(candidate.get("weight"), default=0.0)
            if need_reduce <= 0:
                break

    by_weight = sorted(positions, key=lambda x: _to_float(x.get("weight"), default=0.0), reverse=True)
    if len(by_weight) >= 5:
        top5_weight = sum(_to_float(item.get("weight"), default=0.0) for item in by_weight[:5])
        if top5_weight > _TOP5_LIMIT:
            need_reduce = top5_weight - _TOP5_LIMIT
            for candidate in sorted(by_weight[:5], key=lambda x: (_to_float(x.get("score"), 0.0), -_to_float(x.get("weight"), 0.0))):
                ts_code = str(candidate.get("ts_code") or "")
                add_risk(ts_code, "top5_concentration", "reduce_concentration", f"top5={top5_weight:.2%}, limit={_TOP5_LIMIT:.2%}")
                _ensure_sell_signal(
                    ts_code=ts_code,
                    updated_rows=updated_signals,
                    updated_map=updated_map,
                    default_strategy_version_id=default_strategy_version_id,
                    trade_date=trade_date,
                    regime=regime,
                    position=candidate,
                    reason_code="top5_concentration",
                )
                need_reduce -= _to_float(candidate.get("weight"), default=0.0)
                if need_reduce <= 0:
                    break

    if len(by_weight) >= 10:
        top10_weight = sum(_to_float(item.get("weight"), default=0.0) for item in by_weight[:10])
        if top10_weight > _TOP10_LIMIT:
            need_reduce = top10_weight - _TOP10_LIMIT
            for candidate in sorted(by_weight[:10], key=lambda x: (_to_float(x.get("score"), 0.0), -_to_float(x.get("weight"), 0.0))):
                ts_code = str(candidate.get("ts_code") or "")
                add_risk(ts_code, "top10_concentration", "reduce_concentration", f"top10={top10_weight:.2%}, limit={_TOP10_LIMIT:.2%}")
                _ensure_sell_signal(
                    ts_code=ts_code,
                    updated_rows=updated_signals,
                    updated_map=updated_map,
                    default_strategy_version_id=default_strategy_version_id,
                    trade_date=trade_date,
                    regime=regime,
                    position=candidate,
                    reason_code="top10_concentration",
                )
                need_reduce -= _to_float(candidate.get("weight"), default=0.0)
                if need_reduce <= 0:
                    break

    if len(by_weight) > _MAX_HOLDINGS:
        overflow = len(by_weight) - _MAX_HOLDINGS
        for candidate in sorted(by_weight, key=lambda x: (_to_float(x.get("score"), 0.0), -_to_float(x.get("weight"), 0.0)))[:overflow]:
            ts_code = str(candidate.get("ts_code") or "")
            add_risk(ts_code, "holding_count_cap", "reduce_position_count", f"positions={len(by_weight)}, limit={_MAX_HOLDINGS}")
            _ensure_sell_signal(
                ts_code=ts_code,
                updated_rows=updated_signals,
                updated_map=updated_map,
                default_strategy_version_id=default_strategy_version_id,
                trade_date=trade_date,
                regime=regime,
                position=candidate,
                reason_code="holding_count_cap",
            )
    elif len(by_weight) < _MIN_HOLDINGS:
        add_risk("__portfolio__", "holding_count_floor", "observe", f"positions={len(by_weight)}, floor={_MIN_HOLDINGS}")

    drawdown_20d, drawdown_days = _calc_drawdown_20d(
        account_id=account_id,
        trade_date=trade_date,
        current_equity=total_equity,
    )
    if drawdown_20d > _DRAWDOWN_L3:
        add_risk("__portfolio__", "drawdown_level3", "force_defensive", f"drawdown_20d={drawdown_20d:.2%}, threshold={_DRAWDOWN_L3:.2%}")
        for row in updated_signals:
            if str(row.get("signal") or "") == "BUY":
                row["signal"] = "HOLD"
                _append_reason_codes(row, "drawdown_block_buy")
        if gross_exposure > 0.30:
            need_reduce = gross_exposure - 0.30
            priority = {"attack": 0, "balanced": 1, "defensive": 2}
            reduce_candidates = sorted(
                positions,
                key=lambda x: (
                    priority.get(str(x.get("position_type") or "balanced"), 1),
                    _to_float(x.get("score"), 0.0),
                    -_to_float(x.get("weight"), 0.0),
                ),
            )
            for candidate in reduce_candidates:
                ts_code = str(candidate.get("ts_code") or "")
                add_risk(ts_code, "drawdown_level3_reduce", "force_reduce", f"gross={gross_exposure:.2%}, target=30%")
                _ensure_sell_signal(
                    ts_code=ts_code,
                    updated_rows=updated_signals,
                    updated_map=updated_map,
                    default_strategy_version_id=default_strategy_version_id,
                    trade_date=trade_date,
                    regime=regime,
                    position=candidate,
                    reason_code="drawdown_level3_reduce",
                )
                need_reduce -= _to_float(candidate.get("weight"), default=0.0)
                if need_reduce <= 0:
                    break
    elif drawdown_20d > _DRAWDOWN_L2:
        add_risk("__portfolio__", "drawdown_level2", "block_new_buy", f"drawdown_20d={drawdown_20d:.2%}, threshold={_DRAWDOWN_L2:.2%}")
        for row in updated_signals:
            if str(row.get("signal") or "") == "BUY":
                row["signal"] = "HOLD"
                _append_reason_codes(row, "drawdown_block_buy")
        for candidate in [item for item in positions if str(item.get("position_type") or "") == "attack"]:
            ts_code = str(candidate.get("ts_code") or "")
            add_risk(ts_code, "drawdown_level2_attack_trim", "reduce_attack", "drawdown level2 requires reducing attack positions")
            _ensure_sell_signal(
                ts_code=ts_code,
                updated_rows=updated_signals,
                updated_map=updated_map,
                default_strategy_version_id=default_strategy_version_id,
                trade_date=trade_date,
                regime=regime,
                position=candidate,
                reason_code="drawdown_level2_attack_trim",
            )
    elif drawdown_20d > _DRAWDOWN_L1:
        add_risk("__portfolio__", "drawdown_level1", "risk_warning", f"drawdown_20d={drawdown_20d:.2%}, threshold={_DRAWDOWN_L1:.2%}")

    _normalize_signal_ranks(updated_signals)
    stats = {
        "position_count": len(positions),
        "gross_exposure": gross_exposure,
        "drawdown_20d": drawdown_20d,
        "drawdown_days": drawdown_days,
    }
    return updated_signals, risk_rows, stats


def _apply_ai_and_risk(
    *,
    trade_date: str,
    signal_rows: list[dict[str, Any]],
    quant_payload: dict[str, Any] | None,
    regime: str,
    degrade_flags: list[str],
    explain_refs: list[str],
    account_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    quant_rows = (quant_payload or {}).get("rows")
    quant_map: dict[str, float] = {}
    if isinstance(quant_rows, list):
        for item in quant_rows:
            if not isinstance(item, dict):
                continue
            ts_code = str(item.get("ts_code") or "").strip().upper()
            if not ts_code:
                continue
            quant_map[ts_code] = _to_float(item.get("total_score"), default=0.0)

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    risk_rows: list[dict[str, Any]] = []
    staging_rows: list[dict[str, Any]] = []
    updated: list[dict[str, Any]] = []

    for row in signal_rows:
        item = dict(row)
        ts_code = str(item.get("ts_code") or "").strip().upper()
        strategy_version_id = str(item.get("strategy_version_id") or "").strip()
        local_score = _to_float(item.get("score"), default=0.0)
        ai_score = quant_map.get(ts_code)

        item["signal_source"] = "local"
        item["degrade_flags"] = list(degrade_flags)
        item["explain_refs"] = list(explain_refs)
        item["score_local"] = local_score

        if ai_score is not None:
            blended = local_score * 0.85 + ai_score * 0.15
            item["score"] = round(blended, 4)
            item["score_ai"] = round(ai_score, 4)
            item["signal_source"] = "ai_hybrid"
            staging_rows.append(
                {
                    "trade_date": trade_date,
                    "strategy_version_id": strategy_version_id,
                    "ts_code": ts_code,
                    "factor_source": "quant-factor-screener",
                    "factor_values": {
                        "score_local": local_score,
                        "score_ai": ai_score,
                        "score_blended": blended,
                    },
                }
            )

        if regime == "risk_off" and str(item.get("signal") or "") == "BUY":
            item["signal"] = "HOLD"
            risk_rows.append(
                {
                    "trade_date": trade_date,
                    "account_id": account_id,
                    "ts_code": ts_code,
                    "rule_code": "risk_off_block_buy",
                    "action": "downgrade_to_hold",
                    "detail": "market regime is risk_off",
                }
            )

        grouped[str(item.get("strategy_version_id") or "")].append(item)

    for version_id, rows in grouped.items():
        rows.sort(key=lambda x: (_to_float(x.get("score"), 0.0), str(x.get("ts_code") or "")), reverse=True)
        for rank, row in enumerate(rows, start=1):
            row["rank"] = rank
            updated.append(row)

    if staging_rows:
        upsert_ai_signal_staging(staging_rows)

    return updated, risk_rows, staging_rows


def run_agent_freedom_daily(
    *,
    trade_date: str | None = None,
    strategy_version_id: str | None = None,
    account_id: str = "main",
) -> dict[str, Any]:
    ensure_agent_freedom_indexes()
    normalized_date = _normalize_date(trade_date)
    start_strategy_job_run(
        job_name="agent_freedom_daily",
        run_date=normalized_date,
        params={
            "strategy_version_id": strategy_version_id or "",
            "account_id": account_id,
        },
    )

    try:
        if not is_trading_day(normalized_date, exchange="SSE"):
            finish_strategy_job_run(
                job_name="agent_freedom_daily",
                run_date=normalized_date,
                status="skipped",
                stats={"reason": "non_trading_day"},
                error_message="",
            )
            return {
                "trade_date": normalized_date,
                "status": "skipped",
                "reason": "non_trading_day",
            }

        quality = _compute_data_quality(normalized_date)
        quality_degraded = not bool(quality.get("ok"))

        pre_degrade_flags: list[str] = []
        signal_result: dict[str, Any]
        try:
            signal_result = generate_strategy_signals_for_date(
                signal_date=normalized_date,
                strategy_version_id=strategy_version_id,
                portfolio_id=STRATEGY_PORTFOLIO_ID,
                portfolio_type="strategy",
            )
        except Exception as exc:
            signal_result = {
                "status": "degraded",
                "reason": f"signal_generate_exception:{exc}",
                "total_upserted": 0,
            }
            pre_degrade_flags.append("signal_generation:failed")

        signal_rows = list_strategy_signals_for_date(
            signal_date=normalized_date,
            strategy_version_id=strategy_version_id,
        )
        signal_source_date = normalized_date
        if not signal_rows:
            fallback_rows, fallback_date = _fallback_signal_rows(
                trade_date=normalized_date,
                strategy_version_id=strategy_version_id,
            )
            if fallback_rows and fallback_date:
                signal_rows = fallback_rows
                signal_source_date = fallback_date
                pre_degrade_flags.append(f"signal_fallback:{fallback_date}")
        market_row = _latest_market_factor_row(normalized_date)
        shenwan_rows = _latest_shenwan_rows(normalized_date)

        skill_payloads, degrade_flags, explain_refs = _call_p0_skills(
            trade_date=normalized_date,
            market_row=market_row,
            signal_rows=signal_rows,
            shenwan_rows=shenwan_rows,
        )
        if pre_degrade_flags:
            degrade_flags.extend(pre_degrade_flags)
        if quality_degraded:
            degrade_flags.append("data_quality:degraded")

        market_record, regime, exposure = _resolve_regime(
            trade_date=normalized_date,
            market_row=market_row,
            findata_payload=skill_payloads.get("findata-toolkit-cn"),
        )
        market_record["degrade_flags"] = degrade_flags
        upsert_market_regime_daily(market_record)

        industry_rows = _build_industry_rotation_rows(
            trade_date=normalized_date,
            shenwan_rows=shenwan_rows,
            sector_payload=skill_payloads.get("sector-rotation-detector"),
        )
        industry_count = replace_industry_rotation_daily(trade_date=normalized_date, rows=industry_rows)

        updated_signals, risk_rows, staging_rows = _apply_ai_and_risk(
            trade_date=normalized_date,
            signal_rows=signal_rows,
            quant_payload=skill_payloads.get("quant-factor-screener"),
            regime=regime,
            degrade_flags=degrade_flags,
            explain_refs=explain_refs,
            account_id=account_id,
        )
        updated_signals, extra_risk_rows, risk_stats = _apply_risk_controls_v1(
            trade_date=normalized_date,
            account_id=account_id,
            regime=regime,
            updated_signals=updated_signals,
        )
        if extra_risk_rows:
            risk_rows.extend(extra_risk_rows)
        updated_count = upsert_strategy_signal_updates(updated_signals)
        risk_count = replace_risk_control_daily(trade_date=normalized_date, account_id=account_id, rows=risk_rows)

        buy_items = [item for item in updated_signals if str(item.get("signal") or "") == "BUY"]
        buy_items.sort(key=lambda x: _to_float(x.get("score"), 0.0), reverse=True)

        sell_items = [item for item in updated_signals if str(item.get("signal") or "") == "SELL"]
        sell_items.sort(key=lambda x: _to_float(x.get("score"), 0.0))

        industry_top = sorted(industry_rows, key=lambda x: _to_float(x.get("score"), 0.0), reverse=True)[:6]

        report_markdown = build_daily_report_markdown(
            trade_date=normalized_date,
            regime=regime,
            regime_reason=str(market_record.get("reason") or ""),
            degrade_flags=degrade_flags,
            buy_items=buy_items,
            sell_items=sell_items,
            risk_items=risk_rows,
            industry_top=industry_top,
        )
        push_result = push_feishu_text(report_markdown)

        report_doc = {
            "trade_date": normalized_date,
            "status": "degraded" if degrade_flags else "success",
            "market_regime": regime,
            "market_exposure": exposure,
            "degrade_flags": degrade_flags,
            "quality": quality,
            "stats": {
                "signal_generate_status": str(signal_result.get("status") or ""),
                "signal_base_upserted": int(signal_result.get("total_upserted") or 0),
                "signal_source_date": signal_source_date,
                "signal_updated": updated_count,
                "risk_triggered": risk_count,
                "industry_rows": industry_count,
                "staging_rows": len(staging_rows),
                "skill_success_count": len(skill_payloads),
                "skill_total_count": len(_SKILL_P0),
                "skill_success_rate": _safe_div(float(len(skill_payloads)), float(len(_SKILL_P0))),
                "skill_degrade_count": len(_SKILL_P0) - len(skill_payloads),
                "portfolio_position_count": int(risk_stats.get("position_count") or 0),
                "portfolio_gross_exposure": float(risk_stats.get("gross_exposure") or 0.0),
                "portfolio_drawdown_20d": float(risk_stats.get("drawdown_20d") or 0.0),
                "portfolio_drawdown_days": int(risk_stats.get("drawdown_days") or 0),
            },
            "report_markdown": report_markdown,
            "push": push_result,
            "explain_refs": explain_refs,
        }
        upsert_agent_report_daily(report_doc)

        status = "degraded" if degrade_flags else "success"
        finish_strategy_job_run(
            job_name="agent_freedom_daily",
            run_date=normalized_date,
            status=status,
            stats={
                "skill_success_rate": report_doc["stats"]["skill_success_rate"],
                "skill_degrade_count": report_doc["stats"]["skill_degrade_count"],
                "report_push_status": str(push_result.get("status") or ""),
                "run_latency_ms": 0,
            },
            error_message="",
        )

        return {
            "trade_date": normalized_date,
            "status": status,
            "degrade_flags": degrade_flags,
            "stats": report_doc["stats"],
            "push": push_result,
        }
    except Exception as exc:
        finish_strategy_job_run(
            job_name="agent_freedom_daily",
            run_date=normalized_date,
            status="failed",
            stats={},
            error_message=str(exc),
        )
        raise


def get_agent_freedom_latest_report(*, trade_date: str | None = None) -> dict[str, Any] | None:
    normalized_date = _normalize_date(trade_date) if trade_date else None
    return get_agent_report_daily(normalized_date)


def list_agent_freedom_runs(
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[dict[str, Any]], int]:
    normalized_start = _normalize_date(start_date) if start_date else None
    normalized_end = _normalize_date(end_date) if end_date else None
    return list_agent_job_runs(
        start_date=normalized_start,
        end_date=normalized_end,
        status=status,
        page=page,
        page_size=page_size,
    )


def list_agent_freedom_skill_calls(
    *,
    trade_date: str | None = None,
    skill_name: str | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[dict[str, Any]], int]:
    normalized_date = _normalize_date(trade_date) if trade_date else None
    return list_skill_call_logs(
        trade_date=normalized_date,
        skill_name=skill_name,
        status=status,
        page=page,
        page_size=page_size,
    )


def _normalize_portfolio_positions_input(positions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for raw in positions:
        if not isinstance(raw, dict):
            continue
        ts_code = _normalize_ts_code(raw.get("ts_code"))
        if not ts_code:
            continue
        item = dict(raw)
        item.pop("_id", None)
        item.pop("account_id", None)
        item.pop("created_at", None)
        item["ts_code"] = ts_code
        quantity = _to_float(item.get("quantity"), default=_to_float(item.get("shares"), default=0.0))
        cost_price = _to_float(item.get("cost_price"), default=_to_float(item.get("avg_cost"), default=0.0))
        item["quantity"] = max(quantity, 0.0)
        item["cost_price"] = max(cost_price, 0.0)
        if "shares" in item:
            item["shares"] = max(_to_float(item.get("shares"), default=quantity), 0.0)
        if "current_price" in item:
            item["current_price"] = _to_float(item.get("current_price"), default=0.0)
        if "market_value" in item:
            item["market_value"] = _to_float(item.get("market_value"), default=0.0)
        if not str(item.get("position_type") or "").strip():
            item["position_type"] = "稳健"
        entry_date = item.get("entry_date")
        if entry_date:
            text = _to_trade_date_text(entry_date)
            if text:
                item["entry_date"] = text
        normalized.append(item)
    return normalized


def _enrich_portfolio_positions(positions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not positions:
        return []

    input_codes = sorted({_normalize_ts_code(item.get("ts_code")) for item in positions if item.get("ts_code")})
    if not input_codes:
        return positions

    stock_map: dict[str, dict[str, Any]] = {}
    symbol_to_code: dict[str, str] = {}
    collection = get_collection("stock_basic")

    cursor = collection.find(
        {"ts_code": {"$in": input_codes}},
        {"_id": 0, "ts_code": 1, "symbol": 1, "name": 1, "industry": 1},
    )
    for row in cursor:
        code = _normalize_ts_code(row.get("ts_code"))
        symbol = str(row.get("symbol") or "").strip().upper()
        if not code:
            continue
        stock_map[code] = row
        if symbol:
            symbol_to_code[symbol] = code

    plain_symbols = sorted({code for code in input_codes if len(code) == 6 and code.isdigit()})
    if plain_symbols:
        symbol_cursor = collection.find(
            {"symbol": {"$in": plain_symbols}},
            {"_id": 0, "ts_code": 1, "symbol": 1, "name": 1, "industry": 1},
        )
        for row in symbol_cursor:
            code = _normalize_ts_code(row.get("ts_code"))
            symbol = str(row.get("symbol") or "").strip().upper()
            if not code or not symbol:
                continue
            symbol_to_code[symbol] = code
            stock_map[code] = row

    resolved_codes = sorted(
        {
            symbol_to_code.get(_normalize_ts_code(item.get("ts_code")), _normalize_ts_code(item.get("ts_code")))
            for item in positions
            if item.get("ts_code")
        }
    )
    latest_price_map = list_latest_daily_prices(resolved_codes)
    enriched: list[dict[str, Any]] = []
    for item in positions:
        doc = dict(item)
        raw_code = _normalize_ts_code(doc.get("ts_code"))
        ts_code = symbol_to_code.get(raw_code, raw_code)
        if not ts_code:
            continue
        doc["ts_code"] = ts_code
        stock = stock_map.get(ts_code, {})
        if not str(doc.get("stock_name") or "").strip():
            doc["stock_name"] = str(stock.get("name") or "").strip()
        if not str(doc.get("industry") or "").strip():
            doc["industry"] = str(stock.get("industry") or "").strip()
        if not str(doc.get("position_type") or "").strip():
            doc["position_type"] = "稳健"

        quantity = _to_float(doc.get("quantity"), default=_to_float(doc.get("shares"), default=0.0))
        market_price = _to_float(
            doc.get("current_price"),
            default=_to_float((latest_price_map.get(ts_code) or {}).get("close"), default=0.0),
        )
        if market_price > 0:
            doc["current_price"] = market_price
        market_value = _to_float(doc.get("market_value"), default=0.0)
        if market_value <= 0 and quantity > 0 and market_price > 0:
            market_value = quantity * market_price
        if market_value > 0:
            doc["market_value"] = market_value
        enriched.append(doc)
    return enriched


def get_agent_portfolio_account(*, account_id: str = "main") -> dict[str, Any] | None:
    ensure_agent_freedom_indexes()
    account = get_collection("portfolio_accounts").find_one({"account_id": account_id}, {"_id": 0})
    if not account:
        return None
    positions = list_portfolio_positions(account_id)
    total_market_value = sum(
        _to_float(item.get("market_value"), default=_to_float(item.get("position_value"), default=0.0))
        for item in positions
    )
    total_equity = _to_float(account.get("total_equity"), default=0.0)
    cash = _to_float(account.get("cash"), default=0.0)
    gross_exposure = _safe_div(total_market_value, max(total_equity, total_market_value + cash, 1.0))
    account["summary"] = {
        "position_count": len(positions),
        "total_market_value": total_market_value,
        "total_equity": total_equity,
        "cash": cash,
        "gross_exposure": gross_exposure,
    }
    return account


def upsert_agent_portfolio_account(
    *,
    account_id: str = "main",
    account_name: str,
    total_equity: float,
    cash: float,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    account_id = str(account_id or "").strip() or "main"
    account_name = str(account_name or "").strip() or account_id
    upsert_portfolio_account(
        account_id=account_id,
        account_name=account_name,
        total_equity=float(total_equity),
        cash=float(cash),
        metadata=metadata or {},
    )
    return get_agent_portfolio_account(account_id=account_id) or {
        "account_id": account_id,
        "account_name": account_name,
        "total_equity": float(total_equity),
        "cash": float(cash),
        "metadata": metadata or {},
    }


def get_agent_portfolio_positions(*, account_id: str = "main") -> dict[str, Any]:
    account_id = str(account_id or "").strip() or "main"
    ensure_agent_freedom_indexes()
    positions = list_portfolio_positions(account_id)
    total_market_value = sum(
        _to_float(item.get("market_value"), default=_to_float(item.get("position_value"), default=0.0))
        for item in positions
    )
    account = get_collection("portfolio_accounts").find_one({"account_id": account_id}, {"_id": 0}) or {}
    total_equity = _to_float(account.get("total_equity"), default=0.0)
    cash = _to_float(account.get("cash"), default=0.0)
    summary = {
        "position_count": len(positions),
        "total_market_value": total_market_value,
        "total_equity": total_equity,
        "cash": cash,
        "gross_exposure": _safe_div(total_market_value, max(total_equity, total_market_value + cash, 1.0)),
    }
    return {"account_id": account_id, "items": positions, "summary": summary}


def upsert_agent_portfolio_positions(
    *,
    account_id: str = "main",
    positions: list[dict[str, Any]],
    snapshot_trade_date: str | None = None,
    replace_all: bool = False,
) -> dict[str, Any]:
    account_id = str(account_id or "").strip() or "main"
    ensure_agent_freedom_indexes()
    normalized_positions = _normalize_portfolio_positions_input(positions)
    enriched_positions = _enrich_portfolio_positions(normalized_positions)
    if replace_all:
        get_collection("portfolio_positions").delete_many({"account_id": account_id})
    upserted = upsert_portfolio_positions(account_id=account_id, positions=enriched_positions)
    snapshot_date = _normalize_date(snapshot_trade_date) if snapshot_trade_date else dt.datetime.now().strftime("%Y%m%d")
    snapshot_rows = replace_portfolio_snapshot(
        account_id=account_id,
        trade_date=snapshot_date,
        positions=enriched_positions,
    )
    payload = get_agent_portfolio_positions(account_id=account_id)
    payload["upserted"] = upserted
    payload["snapshot_trade_date"] = snapshot_date
    payload["snapshot_rows"] = snapshot_rows
    payload["replace_all"] = bool(replace_all)
    return payload
