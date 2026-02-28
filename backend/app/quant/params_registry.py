from __future__ import annotations

import math
from typing import Any

from app.quant.engine import DEFAULT_BACKTEST_PARAMS

DEFAULT_STRATEGY_KEY = "multifactor_v1"
PARAMS_SCHEMA_VERSION = "v1"
SUPPORTED_STRATEGY_KEYS = {"multifactor_v1", "musecat_v1"}

_VALID_BOARDS = {"sh_main", "sz_main", "star", "gem", "bse", "other"}

_INT_KEYS = {
    "max_positions",
    "max_hold_days",
    "sell_confirm_days",
    "signal_store_topk",
    "min_hold_days_before_rotate",
    "max_daily_buy_count",
    "max_daily_sell_count",
    "max_daily_trade_count",
    "max_daily_rotate_count",
    "reentry_cooldown_days",
    "annual_trade_window_days",
    "max_annual_trade_count",
    "max_annual_buy_count",
    "max_annual_sell_count",
}

_FLOAT_KEYS = {
    "buy_threshold",
    "sell_threshold",
    "stop_loss_pct",
    "trail_stop_pct",
    "min_avg_amount_20d",
    "slot_weight",
    "rotate_score_delta",
    "rotate_profit_ceiling",
    "sector_max",
    "score_ceiling",
    "slot_min_scale",
    "entry_min_sector_strength",
    "entry_sector_strength_quantile",
    "entry_rsi_min",
    "entry_rsi_max",
    "entry_max_pct_chg",
    "min_gross_exposure",
    "market_exposure_floor",
    "musecat_breakout_bonus",
    "musecat_drawdown_penalty",
    "musecat_macd_zero_axis_cross_bonus",
    "musecat_macd_zero_axis_depth_scale",
}

_BOOL_KEYS = {
    "enable_buy_tech_filter",
    "entry_require_trend_alignment",
    "entry_require_macd_positive",
    "allow_buy_in_risk_off",
    "use_member_sector_mapping",
    "entry_require_macd_zero_axis_cross",
}

_ALPHA_DISALLOWED_KEYS = {
    "musecat_factor_weights",
    "musecat_breakout_bonus",
    "musecat_drawdown_penalty",
}

_MUSECAT_DISALLOWED_KEYS = {
    "factor_weights",
}


class ParamsValidationError(ValueError):
    pass


def _to_float(value: Any, default: float) -> float:
    if value is None or value == "":
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(number):
        return default
    return number


def _to_int(value: Any, default: int) -> int:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_bool(value: Any, default: bool) -> bool:
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


def normalize_strategy_key(value: Any) -> str:
    key = str(value or "").strip()
    if not key:
        return DEFAULT_STRATEGY_KEY
    return key


def _normalize_allowed_boards(value: Any) -> list[str]:
    if isinstance(value, str):
        tokens = [item.strip().lower() for item in value.split(",")]
    elif isinstance(value, (list, tuple, set)):
        tokens = [str(item).strip().lower() for item in value]
    else:
        tokens = []
    allowed = []
    for token in tokens:
        if token in _VALID_BOARDS and token not in allowed:
            allowed.append(token)
    if not allowed:
        return ["sh_main", "sz_main", "star", "gem"]
    return allowed


def _normalize_market_exposure(value: Any, default: dict[str, float]) -> dict[str, float]:
    source = value if isinstance(value, dict) else {}
    return {
        "risk_on": max(_to_float(source.get("risk_on"), default["risk_on"]), 0.0),
        "neutral": max(_to_float(source.get("neutral"), default["neutral"]), 0.0),
        "risk_off": max(_to_float(source.get("risk_off"), default["risk_off"]), 0.0),
    }


def _normalize_sector_source_weights(value: Any, default: dict[str, float]) -> dict[str, float]:
    source = value if isinstance(value, dict) else {}
    sw = max(_to_float(source.get("sw"), default.get("sw", 0.6)), 0.0)
    ci = max(_to_float(source.get("ci"), default.get("ci", 0.4)), 0.0)
    total = sw + ci
    if total <= 0:
        return {"sw": 0.6, "ci": 0.4}
    return {"sw": sw / total, "ci": ci / total}


def _normalize_score_direction(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"reverse", "inverse", "contrarian", "contra"}:
        return "reverse"
    return "normal"


def _normalize_factor_weights(value: Any, default: dict[str, float]) -> dict[str, float]:
    source = value if isinstance(value, dict) else {}
    parsed: dict[str, float] = {}
    for key, default_weight in default.items():
        parsed[key] = max(_to_float(source.get(key), default_weight), 0.0)
    total = sum(parsed.values())
    if total <= 0:
        return dict(default)
    return {key: weight / total for key, weight in parsed.items()}


def _build_musecat_defaults() -> dict[str, Any]:
    defaults = dict(DEFAULT_BACKTEST_PARAMS)
    defaults.pop("factor_weights", None)
    defaults.update(
        {
            "buy_threshold": 72.0,
            "sell_threshold": 48.0,
            "stop_loss_pct": 0.075,
            "trail_stop_pct": 0.095,
            "musecat_factor_weights": {
                "momentum": 0.35,
                "reversal": 0.20,
                "quality": 0.25,
                "liquidity": 0.20,
            },
            "musecat_breakout_bonus": 5.0,
            "musecat_drawdown_penalty": 6.0,
            "musecat_macd_zero_axis_cross_bonus": 8.0,
            "musecat_macd_zero_axis_depth_scale": 3.0,
            "entry_require_macd_zero_axis_cross": False,
            "universe_index_code": "000905.SH",
        }
    )
    return defaults


DEFAULT_PARAMS_BY_KEY: dict[str, dict[str, Any]] = {
    "multifactor_v1": dict(DEFAULT_BACKTEST_PARAMS),
    "musecat_v1": _build_musecat_defaults(),
}


def _normalize_known_keys(merged: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    for key in _INT_KEYS:
        if key in merged:
            merged[key] = max(_to_int(merged.get(key), _to_int(defaults.get(key), 0)), 0)
    for key in _FLOAT_KEYS:
        if key in merged:
            merged[key] = _to_float(merged.get(key), _to_float(defaults.get(key), 0.0))
    for key in _BOOL_KEYS:
        if key in merged:
            merged[key] = _to_bool(merged.get(key), _to_bool(defaults.get(key), False))

    merged["score_direction"] = _normalize_score_direction(merged.get("score_direction"))
    merged["allowed_boards"] = _normalize_allowed_boards(merged.get("allowed_boards"))
    merged["market_exposure"] = _normalize_market_exposure(
        merged.get("market_exposure"),
        defaults.get("market_exposure") if isinstance(defaults.get("market_exposure"), dict) else {"risk_on": 1.0, "neutral": 0.7, "risk_off": 0.4},
    )
    merged["sector_source_weights"] = _normalize_sector_source_weights(
        merged.get("sector_source_weights"),
        defaults.get("sector_source_weights") if isinstance(defaults.get("sector_source_weights"), dict) else {"sw": 0.6, "ci": 0.4},
    )
    return merged


_STRING_KEYS_MUSECAT = {"universe_index_code"}


def _validate_payload_keys(strategy_key: str, payload: dict[str, Any]) -> None:
    allowed_keys = set(DEFAULT_PARAMS_BY_KEY[strategy_key].keys()) | {"strategy_key"}
    if strategy_key == "musecat_v1":
        allowed_keys |= _STRING_KEYS_MUSECAT
    unknown = sorted(key for key in payload.keys() if key not in allowed_keys)
    if unknown:
        raise ParamsValidationError(f"unknown params for {strategy_key}: {', '.join(unknown)}")

    disallowed = _ALPHA_DISALLOWED_KEYS if strategy_key == "multifactor_v1" else _MUSECAT_DISALLOWED_KEYS
    hit = sorted(key for key in payload.keys() if key in disallowed)
    if hit:
        raise ParamsValidationError(f"params not allowed for {strategy_key}: {', '.join(hit)}")


def validate_and_normalize_params(strategy_key: str, params_snapshot: dict[str, Any] | None) -> tuple[dict[str, Any], str]:
    key = normalize_strategy_key(strategy_key)
    if key not in SUPPORTED_STRATEGY_KEYS:
        raise ParamsValidationError(f"unsupported strategy_key: {strategy_key}")

    payload = params_snapshot or {}
    if not isinstance(payload, dict):
        raise ParamsValidationError("params_snapshot must be object")

    _validate_payload_keys(key, payload)

    defaults = dict(DEFAULT_PARAMS_BY_KEY[key])
    merged = dict(defaults)
    for name, value in payload.items():
        if name == "strategy_key":
            continue
        merged[name] = value

    if key == "multifactor_v1":
        merged["factor_weights"] = _normalize_factor_weights(
            merged.get("factor_weights"),
            defaults.get("factor_weights") if isinstance(defaults.get("factor_weights"), dict) else {
                "stock_trend": 0.35,
                "sector_strength": 0.25,
                "value_quality": 0.25,
                "liquidity_stability": 0.15,
            },
        )
    elif key == "musecat_v1":
        merged["musecat_factor_weights"] = _normalize_factor_weights(
            merged.get("musecat_factor_weights"),
            defaults.get("musecat_factor_weights")
            if isinstance(defaults.get("musecat_factor_weights"), dict)
            else {"momentum": 0.35, "reversal": 0.20, "quality": 0.25, "liquidity": 0.20},
        )

    merged = _normalize_known_keys(merged, defaults)
    merged["strategy_key"] = key
    return merged, PARAMS_SCHEMA_VERSION
