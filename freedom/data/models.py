from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable, List, Sequence


@dataclass(frozen=True)
class BasicInfo:
    """
    Basic metadata for a security.

    Attributes:
        ts_code: Unique ticker with market suffix (e.g., 600000.SH).
        name: Security name.
        market: Market identifier (e.g., SH, SZ, BJ).
        list_date: Listing date.
        is_active: Whether the security is currently active/tradable.
        industry: Optional industry label.
    """

    ts_code: str
    name: str
    market: str
    list_date: date
    is_active: bool = True
    industry: str | None = None


@dataclass(frozen=True)
class DailyBar:
    """
    Daily OHLCV bar for a security.

    Attributes mirror the minimum required field set from the README.
    """

    ts_code: str
    trade_date: date
    open: float
    high: float
    low: float
    close: float
    pre_close: float
    pct_chg: float
    vol: float
    amount: float
    turnover_rate: float | None = None


def ensure_unique(items: Sequence[BasicInfo] | Sequence[DailyBar]) -> List:
    """
    Ensure the input list contains unique primary keys.

    Raises:
        ValueError: if duplicate (ts_code, trade_date) pairs are found
        for daily bars, or duplicate ts_code for basic info.
    """

    seen = set()
    output = []
    for item in items:
        if isinstance(item, DailyBar):
            key = (item.ts_code, item.trade_date)
        elif isinstance(item, BasicInfo):
            key = (item.ts_code,)
        else:
            raise TypeError(f"Unsupported type: {type(item)}")

        if key in seen:
            raise ValueError(f"Duplicate primary key detected: {key}")
        seen.add(key)
        output.append(item)
    return output


def coerce_date(value: str | date) -> date:
    """
    Convert YYYY-MM-DD string or date into a date object.
    """

    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


def coerce_basic_info(records: Iterable[dict]) -> List[BasicInfo]:
    """
    Convert iterable of dicts to BasicInfo instances.
    """

    infos = [
        BasicInfo(
            ts_code=rec["ts_code"],
            name=rec["name"],
            market=rec["market"],
            list_date=coerce_date(rec["list_date"]),
            is_active=bool(rec.get("is_active", True)),
            industry=rec.get("industry"),
        )
        for rec in records
    ]
    return ensure_unique(infos)


def coerce_daily_bars(records: Iterable[dict]) -> List[DailyBar]:
    """
    Convert iterable of dicts to DailyBar instances.
    """

    bars = [
        DailyBar(
            ts_code=rec["ts_code"],
            trade_date=coerce_date(rec["trade_date"]),
            open=float(rec["open"]),
            high=float(rec["high"]),
            low=float(rec["low"]),
            close=float(rec["close"]),
            pre_close=float(rec["pre_close"]),
            pct_chg=float(rec["pct_chg"]),
            vol=float(rec["vol"]),
            amount=float(rec["amount"]),
            turnover_rate=float(rec["turnover_rate"]) if rec.get("turnover_rate") is not None else None,
        )
        for rec in records
    ]
    return ensure_unique(bars)
