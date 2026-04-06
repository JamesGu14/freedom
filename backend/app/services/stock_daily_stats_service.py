from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import pandas as pd

from app.api.stock_code import resolve_ts_codes_input
from app.data.stock_daily_stats import (
    get_latest_trade_date,
    list_active_citic_member_codes,
    list_active_shenwan_member_codes,
    list_open_trade_dates,
    list_recent_open_trade_dates,
    list_stock_basics_for_screen,
    load_daily_frame_for_screen,
)
from app.schemas.stock_daily_stats import (
    StockDailyStatsScreenRequest,
    StockDailyStatsScreenResult,
)

SUPPORTED_UNIVERSES = {"all_a", "main_board", "chi_next", "star"}
SUPPORTED_INDUSTRY_SOURCES = {"sw", "citic"}
SUPPORTED_SORT_FIELDS = {"up_days", "pct_change", "max_up_streak", "avg_amount"}
UNIVERSE_MARKETS: dict[str, list[str] | None] = {
    "all_a": None,
    "main_board": ["主板"],
    "chi_next": ["创业板"],
    "star": ["科创板"],
}


@dataclass(slots=True)
class ResolvedTradeDateRange:
    start_date: str | None
    end_date: str | None
    trade_dates: list[str]


@dataclass(slots=True)
class NormalizedScreenRequest:
    start_date: str | None
    end_date: str | None
    lookback_days: int | None
    universe: str
    ts_codes: list[str]
    industry_source: str | None
    industry_codes: list[str]
    up_days_gte: int | None
    pct_change_gte: float | None
    max_up_streak_gte: int | None
    avg_amount_gte: float | None
    exclude_st: bool
    exclude_suspended: bool
    sort_by: str
    sort_order: str
    page: int
    page_size: int


def _normalize_date_text(value: str | None) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    text = text.replace("-", "")
    if len(text) != 8 or not text.isdigit():
        raise ValueError(f"invalid date: {value}")
    return text


def _normalize_positive_int(value: Any, *, field_name: str, allow_none: bool = True) -> int | None:
    if value is None and allow_none:
        return None
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an integer") from exc
    return normalized


def _normalize_non_negative_float(value: Any, *, field_name: str) -> float | None:
    if value is None:
        return None
    try:
        normalized = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a number") from exc
    return normalized


def normalize_screen_request(payload: StockDailyStatsScreenRequest) -> NormalizedScreenRequest:
    start_date = _normalize_date_text(payload.start_date)
    end_date = _normalize_date_text(payload.end_date)
    if start_date and end_date and start_date > end_date:
        raise ValueError("start_date cannot be after end_date")

    lookback_days = _normalize_positive_int(payload.lookback_days, field_name="lookback_days")
    if lookback_days is not None and lookback_days <= 0:
        raise ValueError("lookback_days must be greater than 0")
    if not start_date and lookback_days is None:
        raise ValueError("either start_date or lookback_days is required")

    universe = str(payload.universe or "all_a").strip().lower() or "all_a"
    if universe not in SUPPORTED_UNIVERSES:
        raise ValueError("universe must be one of: all_a/main_board/chi_next/star")

    ts_codes = resolve_ts_codes_input([str(code or "") for code in (payload.ts_codes or [])])
    industry_codes = []
    for code in payload.industry_codes or []:
        text = str(code or "").strip().upper()
        if text and text not in industry_codes:
            industry_codes.append(text)
    industry_source = str(payload.industry_source or "").strip().lower() or None
    if industry_source and industry_source not in SUPPORTED_INDUSTRY_SOURCES:
        raise ValueError("industry_source must be one of: sw/citic")
    if industry_codes and industry_source is None:
        raise ValueError("industry_source is required when industry_codes is provided")

    up_days_gte = _normalize_positive_int(payload.up_days_gte, field_name="up_days_gte")
    max_up_streak_gte = _normalize_positive_int(payload.max_up_streak_gte, field_name="max_up_streak_gte")
    if up_days_gte is not None and up_days_gte < 0:
        raise ValueError("up_days_gte must be greater than or equal to 0")
    if max_up_streak_gte is not None and max_up_streak_gte < 0:
        raise ValueError("max_up_streak_gte must be greater than or equal to 0")

    pct_change_gte = _normalize_non_negative_float(payload.pct_change_gte, field_name="pct_change_gte")
    avg_amount_gte = _normalize_non_negative_float(payload.avg_amount_gte, field_name="avg_amount_gte")

    sort_by = str(payload.sort_by or "up_days").strip().lower() or "up_days"
    if sort_by not in SUPPORTED_SORT_FIELDS:
        raise ValueError("sort_by must be one of: up_days/pct_change/max_up_streak/avg_amount")
    sort_order = str(payload.sort_order or "desc").strip().lower() or "desc"
    if sort_order not in {"asc", "desc"}:
        raise ValueError("sort_order must be one of: asc/desc")

    page = _normalize_positive_int(payload.page, field_name="page", allow_none=False)
    page_size = _normalize_positive_int(payload.page_size, field_name="page_size", allow_none=False)
    if page is None or page <= 0:
        raise ValueError("page must be greater than 0")
    if page_size is None or page_size <= 0:
        raise ValueError("page_size must be greater than 0")
    if page_size > 2000:
        raise ValueError("page_size must be less than or equal to 2000")

    return NormalizedScreenRequest(
        start_date=start_date,
        end_date=end_date,
        lookback_days=lookback_days,
        universe=universe,
        ts_codes=ts_codes,
        industry_source=industry_source,
        industry_codes=industry_codes,
        up_days_gte=up_days_gte,
        pct_change_gte=pct_change_gte,
        max_up_streak_gte=max_up_streak_gte,
        avg_amount_gte=avg_amount_gte,
        exclude_st=bool(payload.exclude_st),
        exclude_suspended=bool(payload.exclude_suspended),
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
    )


def resolve_screen_trade_dates(
    request: NormalizedScreenRequest,
    *,
    latest_trade_date_getter: Callable[..., str | None] = get_latest_trade_date,
    open_trade_dates_getter: Callable[..., list[str]] = list_open_trade_dates,
    recent_trade_dates_getter: Callable[..., list[str]] = list_recent_open_trade_dates,
) -> ResolvedTradeDateRange:
    requested_end_date = request.end_date
    end_date = latest_trade_date_getter(exchange="SSE", before_or_on=requested_end_date)

    if not end_date:
        return ResolvedTradeDateRange(start_date=None, end_date=None, trade_dates=[])

    if request.start_date:
        trade_dates = open_trade_dates_getter(start_date=request.start_date, end_date=end_date, exchange="SSE")
    else:
        trade_dates = recent_trade_dates_getter(
            end_date=end_date,
            limit=int(request.lookback_days or 0),
            exchange="SSE",
        )

    if not trade_dates:
        return ResolvedTradeDateRange(start_date=None, end_date=None, trade_dates=[])
    return ResolvedTradeDateRange(
        start_date=trade_dates[0],
        end_date=trade_dates[-1],
        trade_dates=trade_dates,
    )


def _max_streak(directions: Sequence[int], target: int) -> int:
    best = 0
    current = 0
    for direction in directions:
        if direction == target:
            current += 1
            best = max(best, current)
        else:
            current = 0
    return best


def build_stock_daily_stats_items(
    daily_df: pd.DataFrame,
    *,
    trade_dates: Sequence[str],
    basics_by_code: Mapping[str, Mapping[str, Any]],
    start_date: str,
    end_date: str,
) -> list[dict[str, Any]]:
    if daily_df.empty or not trade_dates:
        return []

    working = daily_df.copy()
    working["ts_code"] = working["ts_code"].astype(str).str.upper()
    working["trade_date"] = working["trade_date"].astype(str)
    working = working[working["trade_date"].isin(list(trade_dates))]
    working = working.drop_duplicates(subset=["ts_code", "trade_date"], keep="last")
    if working.empty:
        return []

    for column in ["close", "pre_close", "pct_chg", "amount"]:
        working[column] = pd.to_numeric(working[column], errors="coerce")
    working = working.dropna(subset=["close", "pre_close", "amount"])
    if working.empty:
        return []

    working["direction"] = 0
    working.loc[working["close"] > working["pre_close"], "direction"] = 1
    working.loc[working["close"] < working["pre_close"], "direction"] = -1
    working["pct_chg_effective"] = working["pct_chg"]
    missing_pct = working["pct_chg_effective"].isna()
    working.loc[missing_pct, "pct_chg_effective"] = (
        (working.loc[missing_pct, "close"] - working.loc[missing_pct, "pre_close"])
        / working.loc[missing_pct, "pre_close"].where(working.loc[missing_pct, "pre_close"] != 0)
        * 100
    )
    working = working.sort_values(["ts_code", "trade_date"], kind="stable")

    items: list[dict[str, Any]] = []
    for ts_code, group in working.groupby("ts_code", sort=False):
        if basics_by_code and ts_code not in basics_by_code:
            continue
        if group.empty:
            continue
        first_row = group.iloc[0]
        last_row = group.iloc[-1]
        first_pre_close = float(first_row["pre_close"])
        last_close = float(last_row["close"])
        latest_pct_chg = last_row["pct_chg_effective"]
        if first_pre_close <= 0 or pd.isna(latest_pct_chg):
            continue

        directions = [int(value) for value in group["direction"].tolist()]
        basic = basics_by_code.get(ts_code, {})
        items.append(
            {
                "ts_code": ts_code,
                "name": basic.get("name"),
                "start_date": start_date,
                "end_date": end_date,
                "trade_days": int(len(group)),
                "up_days": int((group["direction"] > 0).sum()),
                "down_days": int((group["direction"] < 0).sum()),
                "flat_days": int((group["direction"] == 0).sum()),
                "pct_change": float((last_close / first_pre_close - 1.0) * 100.0),
                "max_up_streak": _max_streak(directions, 1),
                "max_down_streak": _max_streak(directions, -1),
                "avg_amount": float(group["amount"].mean()),
                "latest_close": last_close,
                "latest_pct_chg": float(latest_pct_chg),
            }
        )
    return items


def filter_sort_paginate_stock_daily_stats(
    items: Sequence[dict[str, Any]],
    request: NormalizedScreenRequest,
    *,
    expected_trade_days: int,
) -> StockDailyStatsScreenResult:
    filtered: list[dict[str, Any]] = []
    for item in items:
        if request.exclude_suspended and int(item["trade_days"]) < expected_trade_days:
            continue
        if request.up_days_gte is not None and int(item["up_days"]) < request.up_days_gte:
            continue
        if request.pct_change_gte is not None and float(item["pct_change"]) < request.pct_change_gte:
            continue
        if request.max_up_streak_gte is not None and int(item["max_up_streak"]) < request.max_up_streak_gte:
            continue
        if request.avg_amount_gte is not None and float(item["avg_amount"]) < request.avg_amount_gte:
            continue
        filtered.append(item)

    reverse = request.sort_order == "desc"
    if reverse:
        filtered.sort(key=lambda row: str(row.get("ts_code") or ""))
        filtered.sort(key=lambda row: float(row.get(request.sort_by) or 0), reverse=True)
    else:
        filtered.sort(key=lambda row: (float(row.get(request.sort_by) or 0), str(row.get("ts_code") or "")))

    total = len(filtered)
    offset = (request.page - 1) * request.page_size
    paged = filtered[offset : offset + request.page_size]
    return StockDailyStatsScreenResult(
        data=paged,
        total=total,
        page=request.page,
        page_size=request.page_size,
    )


def _is_st_name(name: str | None) -> bool:
    text = str(name or "").strip().upper()
    return text.startswith("ST") or text.startswith("*ST")


def _filter_basics_by_industry(
    basics: Sequence[dict[str, Any]],
    *,
    industry_source: str | None,
    industry_codes: Sequence[str],
    trade_date: str,
) -> list[dict[str, Any]]:
    if not industry_codes or not industry_source:
        return list(basics)

    if industry_source == "sw":
        allowed_codes = list_active_shenwan_member_codes(industry_codes=industry_codes, trade_date=trade_date)
    else:
        allowed_codes = list_active_citic_member_codes(industry_codes=industry_codes, trade_date=trade_date)
    if not allowed_codes:
        return []
    return [
        item
        for item in basics
        if str(item.get("ts_code") or "").strip().upper() in allowed_codes
    ]


def screen_stock_daily_stats(payload: StockDailyStatsScreenRequest) -> StockDailyStatsScreenResult:
    request = normalize_screen_request(payload)
    resolved = resolve_screen_trade_dates(request)
    if not resolved.trade_dates or not resolved.start_date or not resolved.end_date:
        return StockDailyStatsScreenResult(data=[], total=0, page=request.page, page_size=request.page_size)

    if request.ts_codes:
        basics = list_stock_basics_for_screen(ts_codes=request.ts_codes)
    else:
        basics = list_stock_basics_for_screen(markets=UNIVERSE_MARKETS[request.universe])

    if request.exclude_st:
        basics = [item for item in basics if not _is_st_name(item.get("name"))]
    basics = _filter_basics_by_industry(
        basics,
        industry_source=request.industry_source,
        industry_codes=request.industry_codes,
        trade_date=resolved.end_date,
    )
    if not basics:
        return StockDailyStatsScreenResult(data=[], total=0, page=request.page, page_size=request.page_size)

    basics_by_code = {
        str(item.get("ts_code") or "").strip().upper(): item
        for item in basics
        if str(item.get("ts_code") or "").strip()
    }
    daily_ts_codes = basics_by_code.keys() if len(basics_by_code) <= 2000 else None
    daily_df = load_daily_frame_for_screen(
        start_date=resolved.start_date,
        end_date=resolved.end_date,
        ts_codes=daily_ts_codes,
    )
    items = build_stock_daily_stats_items(
        daily_df,
        trade_dates=resolved.trade_dates,
        basics_by_code=basics_by_code,
        start_date=resolved.start_date,
        end_date=resolved.end_date,
    )
    return filter_sort_paginate_stock_daily_stats(
        items,
        request,
        expected_trade_days=len(resolved.trade_dates),
    )
