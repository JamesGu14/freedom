from __future__ import annotations

import re

from app.data.mongo_stock import get_ts_code_by_symbol

_PREFIX_PATTERN = re.compile(r"^(SH|SZ|BJ)(\d{6})$", re.IGNORECASE)
_SUFFIX_PATTERN = re.compile(r"^(\d{6})(SH|SZ|BJ)$", re.IGNORECASE)
_SYMBOL_PATTERN = re.compile(r"^\d{6}$")


def _infer_exchange(symbol: str) -> str | None:
    if not symbol:
        return None
    first = symbol[0]
    if first in {"5", "6", "9"}:
        return "SH"
    if first in {"0", "1", "2", "3"}:
        return "SZ"
    if first in {"4", "8"}:
        return "BJ"
    return None


def resolve_ts_code_input(value: str, *, strict: bool = False) -> str:
    text = str(value or "").strip().upper()
    if not text:
        raise ValueError("ts_code is required")

    if "." in text:
        return text

    match = _PREFIX_PATTERN.match(text)
    if match:
        return f"{match.group(2)}.{match.group(1)}"

    match = _SUFFIX_PATTERN.match(text)
    if match:
        return f"{match.group(1)}.{match.group(2)}"

    if _SYMBOL_PATTERN.match(text):
        mapped = get_ts_code_by_symbol(text)
        if mapped:
            return str(mapped).strip().upper()
        inferred = _infer_exchange(text)
        if inferred:
            return f"{text}.{inferred}"

    if strict:
        raise ValueError(f"invalid stock code: {value}")
    return text


def resolve_ts_codes_input(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        code = resolve_ts_code_input(value, strict=False)
        if code:
            result.append(code)
    return list(dict.fromkeys(result))

