from __future__ import annotations

from typing import Any

_INDICATOR_FIELDS: list[dict[str, Any]] = [
    {"field": "close_qfq", "type": "number", "filterable": True, "aliases": ["close_qfq"]},
    {"field": "ma5", "type": "number", "filterable": True, "aliases": ["ma5", "ma_qfq_5"]},
    {"field": "ma10", "type": "number", "filterable": True, "aliases": ["ma10", "ma_qfq_10"]},
    {"field": "ma20", "type": "number", "filterable": True, "aliases": ["ma20", "ma_qfq_20"]},
    {"field": "ma30", "type": "number", "filterable": True, "aliases": ["ma30", "ma_qfq_30"]},
    {"field": "ma60", "type": "number", "filterable": True, "aliases": ["ma60", "ma_qfq_60"]},
    {"field": "ma90", "type": "number", "filterable": True, "aliases": ["ma90", "ma_qfq_90"]},
    {"field": "ma250", "type": "number", "filterable": True, "aliases": ["ma250", "ma_qfq_250"]},
    {"field": "macd", "type": "number", "filterable": True, "aliases": ["macd", "macd_dif", "macd_dif_qfq"]},
    {
        "field": "macd_signal",
        "type": "number",
        "filterable": True,
        "aliases": ["macd_signal", "macd_dea", "macd_dea_qfq"],
    },
    {"field": "macd_hist", "type": "number", "filterable": True, "aliases": ["macd_hist", "macd_qfq"]},
    {"field": "kdj_k", "type": "number", "filterable": True, "aliases": ["kdj_k", "kdj_k_qfq"]},
    {"field": "kdj_d", "type": "number", "filterable": True, "aliases": ["kdj_d", "kdj_d_qfq"]},
    {"field": "kdj_j", "type": "number", "filterable": True, "aliases": ["kdj_j", "kdj_qfq"]},
    {"field": "boll_upper", "type": "number", "filterable": True, "aliases": ["boll_upper", "boll_upper_qfq"]},
    {
        "field": "boll_middle",
        "type": "number",
        "filterable": True,
        "aliases": ["boll_middle", "boll_mid", "boll_mid_qfq"],
    },
    {"field": "boll_lower", "type": "number", "filterable": True, "aliases": ["boll_lower", "boll_lower_qfq"]},
    {"field": "rsi6", "type": "number", "filterable": True, "aliases": ["rsi6", "rsi_qfq_6"]},
    {"field": "rsi12", "type": "number", "filterable": True, "aliases": ["rsi12", "rsi_qfq_12"]},
    {"field": "rsi24", "type": "number", "filterable": True, "aliases": ["rsi24", "rsi_qfq_24"]},
    {"field": "atr", "type": "number", "filterable": True, "aliases": ["atr", "atr_qfq"]},
    {"field": "cci", "type": "number", "filterable": True, "aliases": ["cci", "cci_qfq"]},
    {"field": "wr", "type": "number", "filterable": True, "aliases": ["wr", "wr_qfq"]},
    {"field": "wr1", "type": "number", "filterable": True, "aliases": ["wr1", "wr1_qfq"]},
    {"field": "updays", "type": "number", "filterable": True, "aliases": ["updays"]},
    {"field": "downdays", "type": "number", "filterable": True, "aliases": ["downdays"]},
    {"field": "pe", "type": "number", "filterable": True, "aliases": ["pe"]},
    {"field": "pe_ttm", "type": "number", "filterable": True, "aliases": ["pe_ttm"]},
    {"field": "pb", "type": "number", "filterable": True, "aliases": ["pb"]},
    {"field": "turnover_rate", "type": "number", "filterable": True, "aliases": ["turnover_rate"]},
    {"field": "turnover_rate_f", "type": "number", "filterable": True, "aliases": ["turnover_rate_f"]},
    {"field": "volume_ratio", "type": "number", "filterable": True, "aliases": ["volume_ratio"]},
]

_BASE_FIELDS = {"ts_code", "trade_date", "year"}
_ALIAS_TO_FIELD: dict[str, str] = {}
for item in _INDICATOR_FIELDS:
    field = str(item["field"])
    _ALIAS_TO_FIELD[field.lower()] = field
    for alias in item.get("aliases", []):
        _ALIAS_TO_FIELD[str(alias).lower()] = field


def list_indicator_fields() -> list[dict[str, Any]]:
    return [dict(item) for item in _INDICATOR_FIELDS]


def indicator_field_names() -> list[str]:
    return [str(item["field"]) for item in _INDICATOR_FIELDS]


def normalize_requested_indicators(
    value: str | list[str] | None,
) -> tuple[list[str], list[str]]:
    raw = _split_indicator_items(value)
    if not raw:
        return indicator_field_names(), []

    selected: list[str] = []
    missing: list[str] = []
    seen: set[str] = set()
    seen_missing: set[str] = set()
    for item in raw:
        lower = item.lower()
        if lower in _BASE_FIELDS:
            continue
        field = _ALIAS_TO_FIELD.get(lower)
        if not field:
            if item not in seen_missing:
                seen_missing.add(item)
                missing.append(item)
            continue
        if field in seen:
            continue
        seen.add(field)
        selected.append(field)
    return selected, missing


def _split_indicator_items(value: str | list[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        parts = [str(item or "").strip() for item in value]
    else:
        parts = [item.strip() for item in str(value).split(",")]
    return [item for item in parts if item]
