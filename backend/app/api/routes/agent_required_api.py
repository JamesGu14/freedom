from __future__ import annotations

import datetime as dt
import re
from typing import Any

import duckdb
import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from pymongo import ASCENDING, DESCENDING

from app.api.stock_code import resolve_ts_code_input, resolve_ts_codes_input
from app.core.config import settings
from app.data.duckdb_store import get_connection
from app.data.mongo import get_collection
from app.data.mongo_citic import list_citic_industry, list_citic_members
from app.data.mongo_citic_daily import list_latest_citic_trade_dates
from app.data.mongo_market_index import list_market_trade_dates
from app.data.mongo_shenwan import (
    get_shenwan_by_index_code,
    get_shenwan_by_industry_code,
    list_shenwan_industry,
    list_shenwan_versions,
)
from app.data.mongo_shenwan_daily import list_latest_trade_dates
from app.data.mongo_shenwan_member import list_shenwan_members
from app.services.indicator_fields_service import (
    list_indicator_fields,
    normalize_requested_indicators,
)
from app.schemas.stock_daily_stats import StockDailyStatsScreenRequest
from app.services.stock_daily_stats_service import screen_stock_daily_stats

router = APIRouter()


class DailyBatchRequest(BaseModel):
    ts_codes: list[str] = Field(default_factory=list)
    trade_date: str
    adj: str = "qfq"


class FinancialIndicatorsBatchRequest(BaseModel):
    ts_codes: list[str] = Field(default_factory=list)
    period: str | None = None
    fields: list[str] = Field(default_factory=list)


def _ok(data: Any, **extra: Any) -> dict[str, Any]:
    payload = {"code": 200, "data": data}
    payload.update(extra)
    return payload


def _normalize_date(value: str | None, *, required: bool = False) -> str | None:
    text = str(value or "").strip()
    if not text:
        if required:
            raise ValueError("date is required, use YYYYMMDD or YYYY-MM-DD")
        return None
    text = text.replace("-", "")
    if len(text) != 8 or not text.isdigit():
        raise ValueError(f"invalid date: {value}")
    return text


def _normalize_ts_code(value: str) -> str:
    return resolve_ts_code_input(value, strict=False)


def _normalize_ts_codes(value: str | list[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        parts = [str(item or "") for item in value]
    else:
        parts = str(value).split(",")
    items = [str(part or "").strip() for part in parts if str(part or "").strip()]
    return resolve_ts_codes_input(items)


def _resolve_exchange(ts_code: str) -> str | None:
    code = str(ts_code or "").upper()
    if code.endswith(".SH"):
        return "SSE"
    if code.endswith(".SZ"):
        return "SZSE"
    if code.endswith(".BJ"):
        return "BSE"
    return None


def _canonical_market(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    upper = text.upper()
    mapping = {
        "MAIN": "主板",
        "GEM": "创业板",
        "STAR": "科创板",
        "主板": "主板",
        "创业板": "创业板",
        "科创板": "科创板",
    }
    return mapping.get(upper, text)


def _safe_fetch_df(query: str, params: list[Any]) -> pd.DataFrame:
    try:
        with get_connection(read_only=True) as con:
            return con.execute(query, params).fetchdf()
    except (duckdb.CatalogException, duckdb.IOException):
        return pd.DataFrame()


def _to_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    if df.empty:
        return []
    normalized = df.where(pd.notna(df), None)
    return normalized.to_dict(orient="records")


def _field_set(fields: str | list[str] | None) -> set[str] | None:
    if fields is None:
        return None
    if isinstance(fields, list):
        values = [str(item or "").strip() for item in fields]
    else:
        values = [item.strip() for item in str(fields or "").split(",")]
    values = [item for item in values if item]
    if not values:
        return None
    return set(values)


def _apply_fields(
    items: list[dict[str, Any]],
    *,
    fields: str | list[str] | None,
    always_keep: set[str] | None = None,
) -> list[dict[str, Any]]:
    wanted = _field_set(fields)
    if not wanted:
        return items
    keep = set(always_keep or set())
    keep.update(wanted)
    return [{k: v for k, v in row.items() if k in keep} for row in items]


def _paginate(items: list[dict[str, Any]], *, page: int, page_size: int) -> tuple[list[dict[str, Any]], int]:
    size = max(1, min(int(page_size), 5000))
    offset = max(int(page) - 1, 0) * size
    total = len(items)
    return items[offset : offset + size], total


def _latest_trade_date_from_parquet(relative_dir: str) -> str | None:
    root = settings.data_dir / relative_dir
    if not root.exists():
        return None
    part_glob = str(root / "ts_code=*" / "year=*" / "part-*.parquet")
    df = _safe_fetch_df("SELECT MAX(trade_date) AS trade_date FROM read_parquet(?, hive_partitioning=1)", [part_glob])
    if df.empty:
        return None
    value = df.iloc[0].get("trade_date")
    return str(value) if value else None


def _latest_trade_date_from_collection(collection: str, field: str = "trade_date") -> str | None:
    row = get_collection(collection).find_one(
        {field: {"$exists": True, "$ne": None, "$ne": ""}},
        {"_id": 0, field: 1},
        sort=[(field, DESCENDING)],
    )
    if not row:
        return None
    value = row.get(field)
    return str(value) if value else None


def _apply_adj(*, ts_code: str, items: list[dict[str, Any]], adj: str) -> list[dict[str, Any]]:
    adj_value = str(adj or "none").strip().lower()
    if adj_value == "none":
        return items
    if adj_value not in {"qfq", "hfq"}:
        raise ValueError("adj must be one of: qfq/hfq/none")
    if not items:
        return items

    df = _safe_fetch_df(
        "SELECT trade_date, adj_factor FROM adj_factor WHERE ts_code = ? ORDER BY trade_date",
        [_normalize_ts_code(ts_code)],
    )
    factors = {
        str(row["trade_date"]): float(row["adj_factor"])
        for row in _to_records(df)
        if row.get("adj_factor") is not None and float(row["adj_factor"]) > 0
    }
    if not factors:
        return items

    values = list(factors.values())
    base = max(values) if adj_value == "qfq" else min(values)
    if base <= 0:
        return items

    price_fields = {"open", "high", "low", "close", "pre_close"}
    adjusted: list[dict[str, Any]] = []
    for row in items:
        trade_date = str(row.get("trade_date") or "")
        factor = factors.get(trade_date)
        if factor is None or factor <= 0:
            adjusted.append(row)
            continue
        ratio = factor / base
        copied = dict(row)
        for key in price_fields:
            value = copied.get(key)
            if isinstance(value, (int, float)):
                copied[key] = round(float(value) * ratio, 6)
        adjusted.append(copied)
    return adjusted


def _resolve_latest_trade_date(exchange: str = "SSE") -> str | None:
    today = dt.datetime.now().strftime("%Y%m%d")
    query = {
        "exchange": exchange,
        "is_open": {"$in": [1, "1"]},
        "cal_date": {"$lte": today},
    }
    row = get_collection("trade_calendar").find_one(query, {"_id": 0, "cal_date": 1}, sort=[("cal_date", DESCENDING)])
    if row and row.get("cal_date"):
        return str(row["cal_date"])
    fallback = get_collection("trade_calendar").find_one(
        {"exchange": exchange, "is_open": {"$in": [1, "1"]}},
        {"_id": 0, "cal_date": 1},
        sort=[("cal_date", DESCENDING)],
    )
    return str(fallback.get("cal_date")) if fallback and fallback.get("cal_date") else None


@router.get("/stocks/basic")
def stocks_basic(
    market: str | None = Query(default=None),
    exchange: str | None = Query(default=None),
    ts_codes: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=200, ge=1, le=2000),
) -> dict[str, Any]:
    query: dict[str, Any] = {}
    market_value = _canonical_market(market)
    if market_value:
        query["market"] = market_value

    code_items = _normalize_ts_codes(ts_codes)
    if code_items:
        query["ts_code"] = {"$in": code_items}

    rows = list(get_collection("stock_basic").find(query, {"_id": 0}).sort("ts_code", ASCENDING))
    items = []
    for row in rows:
        item = dict(row)
        item["ts_code"] = str(item.get("ts_code") or "").upper()
        item["exchange"] = _resolve_exchange(item.get("ts_code") or "")
        items.append(item)

    exchange_value = str(exchange or "").strip().upper()
    if exchange_value:
        items = [item for item in items if str(item.get("exchange") or "").upper() == exchange_value]

    paged, total = _paginate(items, page=page, page_size=page_size)
    return _ok(paged, total=total, page=page, page_size=page_size)


@router.get("/stocks/basic/{ts_code}")
def stock_basic_detail(ts_code: str) -> dict[str, Any]:
    code = _normalize_ts_code(ts_code)
    row = get_collection("stock_basic").find_one({"ts_code": code}, {"_id": 0})
    if not row:
        raise HTTPException(status_code=404, detail="stock not found")
    item = dict(row)
    item["exchange"] = _resolve_exchange(code)
    return _ok(item)


@router.get("/stocks/search")
def stocks_search(
    q: str = Query(..., min_length=1),
    limit: int = Query(default=20, ge=1, le=200),
) -> dict[str, Any]:
    pattern = re.escape(str(q).strip())
    cursor = (
        get_collection("stock_basic")
        .find(
            {
                "$or": [
                    {"ts_code": {"$regex": pattern, "$options": "i"}},
                    {"symbol": {"$regex": pattern, "$options": "i"}},
                    {"name": {"$regex": pattern, "$options": "i"}},
                ]
            },
            {"_id": 0},
        )
        .sort("ts_code", ASCENDING)
        .limit(limit)
    )
    items = []
    for row in cursor:
        item = dict(row)
        item["exchange"] = _resolve_exchange(item.get("ts_code") or "")
        items.append(item)
    return _ok(items, total=len(items))


@router.get("/stocks/{ts_code}/daily")
def stock_daily(
    ts_code: str,
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    adj: str = Query(default="none"),
    fields: str | None = Query(default=None),
) -> dict[str, Any]:
    try:
        code = _normalize_ts_code(ts_code)
        start = _normalize_date(start_date)
        end = _normalize_date(end_date)
        root = settings.data_dir / "raw" / "daily" / f"ts_code={code}"
        if not root.exists():
            return _ok([])
        part_glob = str(root / "year=*" / "part-*.parquet")
        query = [
            "SELECT ts_code, trade_date, open, high, low, close, pre_close, change, pct_chg, vol, amount",
            "FROM read_parquet(?, union_by_name=true)",
            "WHERE ts_code = ?",
        ]
        params: list[Any] = [part_glob, code]
        if start:
            query.append("AND trade_date >= ?")
            params.append(start)
        if end:
            query.append("AND trade_date <= ?")
            params.append(end)
        query.append("ORDER BY trade_date")
        items = _to_records(_safe_fetch_df(" ".join(query), params))
        items = _apply_adj(ts_code=code, items=items, adj=adj)
        items = _apply_fields(items, fields=fields, always_keep={"ts_code", "trade_date"})
        return _ok(items)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/stocks/daily/batch")
def stock_daily_batch(payload: DailyBatchRequest) -> dict[str, Any]:
    try:
        date_value = _normalize_date(payload.trade_date, required=True)
        codes = _normalize_ts_codes(payload.ts_codes)
        if not codes:
            return _ok([])

        year = str(date_value)[:4]
        part_glob = str(settings.data_dir / "raw" / "daily" / "ts_code=*" / f"year={year}" / "part-*.parquet")
        placeholders = ", ".join(["?"] * len(codes))
        df = _safe_fetch_df(
            f"""
            SELECT ts_code, trade_date, open, high, low, close, pre_close, change, pct_chg, vol, amount
            FROM read_parquet(?, hive_partitioning=1, union_by_name=true)
            WHERE trade_date = ? AND ts_code IN ({placeholders})
            ORDER BY ts_code
            """,
            [part_glob, date_value, *codes],
        )
        items = _to_records(df)
        if str(payload.adj or "none").lower() != "none":
            grouped: dict[str, list[dict[str, Any]]] = {}
            for row in items:
                grouped.setdefault(str(row.get("ts_code") or ""), []).append(row)
            merged: list[dict[str, Any]] = []
            for code, rows in grouped.items():
                merged.extend(_apply_adj(ts_code=code, items=rows, adj=payload.adj))
            items = sorted(merged, key=lambda x: str(x.get("ts_code") or ""))
        return _ok(items, total=len(items), trade_date=date_value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/stocks/{ts_code}/daily/recent")
def stock_daily_recent(
    ts_code: str,
    n: int = Query(..., ge=1, le=4000),
    adj: str = Query(default="qfq"),
    fields: str | None = Query(default=None),
) -> dict[str, Any]:
    try:
        code = _normalize_ts_code(ts_code)
        root = settings.data_dir / "raw" / "daily" / f"ts_code={code}"
        if not root.exists():
            return _ok([])
        part_glob = str(root / "year=*" / "part-*.parquet")
        df = _safe_fetch_df(
            """
            SELECT ts_code, trade_date, open, high, low, close, pre_close, change, pct_chg, vol, amount
            FROM read_parquet(?, union_by_name=true)
            WHERE ts_code = ?
            ORDER BY trade_date DESC
            LIMIT ?
            """,
            [part_glob, code, n],
        )
        items = _to_records(df)
        items.reverse()
        items = _apply_adj(ts_code=code, items=items, adj=adj)
        items = _apply_fields(items, fields=fields, always_keep={"ts_code", "trade_date"})
        return _ok(items, total=len(items))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/stocks/daily/snapshot")
def daily_snapshot(
    trade_date: str | None = Query(default=None),
    ts_codes: str | None = Query(default=None),
    fields: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=500, ge=1, le=5000),
) -> dict[str, Any]:
    try:
        date_value = _normalize_date(trade_date)
        if not date_value:
            date_value = _latest_trade_date_from_parquet("raw/daily")
        if not date_value:
            return _ok([], total=0, trade_date=None)

        year = date_value[:4]
        part_glob = str(settings.data_dir / "raw" / "daily" / "ts_code=*" / f"year={year}" / "part-*.parquet")
        query = [
            "SELECT ts_code, trade_date, open, high, low, close, pre_close, change, pct_chg, vol, amount",
            "FROM read_parquet(?, hive_partitioning=1, union_by_name=true)",
            "WHERE trade_date = ?",
        ]
        params: list[Any] = [part_glob, date_value]
        codes = _normalize_ts_codes(ts_codes)
        if codes:
            placeholders = ", ".join(["?"] * len(codes))
            query.append(f"AND ts_code IN ({placeholders})")
            params.extend(codes)
        query.append("ORDER BY ts_code")
        rows = _to_records(_safe_fetch_df(" ".join(query), params))
        rows = _apply_fields(rows, fields=fields, always_keep={"ts_code", "trade_date"})
        paged, total = _paginate(rows, page=page, page_size=page_size)
        return _ok(paged, total=total, trade_date=date_value, page=page, page_size=page_size)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/stocks/daily/stats/screen")
def stock_daily_stats_screen(payload: StockDailyStatsScreenRequest) -> dict[str, Any]:
    try:
        result = screen_stock_daily_stats(payload)
        return _ok(result.data, total=result.total, page=result.page, page_size=result.page_size)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/stocks/{ts_code}/daily-basic")
def stock_daily_basic(
    ts_code: str,
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    fields: str | None = Query(default=None),
) -> dict[str, Any]:
    try:
        code = _normalize_ts_code(ts_code)
        start = _normalize_date(start_date)
        end = _normalize_date(end_date)
        root = settings.data_dir / "raw" / "daily_basic" / f"ts_code={code}"
        if not root.exists():
            return _ok([])
        part_glob = str(root / "year=*" / "part-*.parquet")
        query = [
            "SELECT ts_code, trade_date, close, turnover_rate, turnover_rate_f, volume_ratio, pe, pe_ttm, pb, ps, ps_ttm,",
            "dv_ratio, dv_ttm, total_share, float_share, free_share, total_mv, circ_mv",
            "FROM read_parquet(?, union_by_name=true)",
            "WHERE ts_code = ?",
        ]
        params: list[Any] = [part_glob, code]
        if start:
            query.append("AND trade_date >= ?")
            params.append(start)
        if end:
            query.append("AND trade_date <= ?")
            params.append(end)
        query.append("ORDER BY trade_date")
        rows = _to_records(_safe_fetch_df(" ".join(query), params))
        rows = _apply_fields(rows, fields=fields, always_keep={"ts_code", "trade_date"})
        return _ok(rows)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/stocks/daily-basic/snapshot")
def daily_basic_snapshot(
    trade_date: str | None = Query(default=None),
    pe_ttm_max: float | None = Query(default=None),
    pb_max: float | None = Query(default=None),
    total_mv_min: float | None = Query(default=None),
    total_mv_max: float | None = Query(default=None),
    dv_ratio_min: float | None = Query(default=None),
    turnover_rate_max: float | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=500, ge=1, le=5000),
    fields: str | None = Query(default=None),
) -> dict[str, Any]:
    try:
        date_value = _normalize_date(trade_date)
        if not date_value:
            date_value = _latest_trade_date_from_parquet("raw/daily_basic")
        if not date_value:
            return _ok([], total=0, trade_date=None)

        year = date_value[:4]
        part_glob = str(settings.data_dir / "raw" / "daily_basic" / "ts_code=*" / f"year={year}" / "part-*.parquet")
        query = [
            "SELECT ts_code, trade_date, close, turnover_rate, turnover_rate_f, volume_ratio, pe, pe_ttm, pb, ps, ps_ttm,",
            "dv_ratio, dv_ttm, total_share, float_share, free_share, total_mv, circ_mv",
            "FROM read_parquet(?, hive_partitioning=1, union_by_name=true)",
            "WHERE trade_date = ?",
        ]
        params: list[Any] = [part_glob, date_value]
        if pe_ttm_max is not None:
            query.append("AND pe_ttm <= ?")
            params.append(float(pe_ttm_max))
        if pb_max is not None:
            query.append("AND pb <= ?")
            params.append(float(pb_max))
        if total_mv_min is not None:
            query.append("AND total_mv >= ?")
            params.append(float(total_mv_min))
        if total_mv_max is not None:
            query.append("AND total_mv <= ?")
            params.append(float(total_mv_max))
        if dv_ratio_min is not None:
            query.append("AND dv_ratio >= ?")
            params.append(float(dv_ratio_min))
        if turnover_rate_max is not None:
            query.append("AND turnover_rate <= ?")
            params.append(float(turnover_rate_max))
        query.append("ORDER BY ts_code")
        rows = _to_records(_safe_fetch_df(" ".join(query), params))
        rows = _apply_fields(rows, fields=fields, always_keep={"ts_code", "trade_date"})
        paged, total = _paginate(rows, page=page, page_size=page_size)
        return _ok(paged, total=total, trade_date=date_value, page=page, page_size=page_size)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/stocks/indicators/fields")
def stock_indicator_fields() -> dict[str, Any]:
    items = list_indicator_fields()
    return _ok(items, total=len(items))


@router.get("/stocks/{ts_code}/indicators")
def stock_indicators(
    ts_code: str,
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    fields: str | None = Query(default=None),
    indicators: str | None = Query(default=None),
    format: str = Query(default="nested"),
) -> dict[str, Any]:
    try:
        code = _normalize_ts_code(ts_code)
        start = _normalize_date(start_date)
        end = _normalize_date(end_date)
        if start and end and start > end:
            raise ValueError("start_date cannot be later than end_date")

        format_value = str(format or "nested").strip().lower()
        if format_value not in {"nested", "records"}:
            raise ValueError("format must be one of: nested/records")

        requested = indicators if indicators is not None else fields
        selected_indicators, missing_indicators = normalize_requested_indicators(requested)

        root = settings.data_dir / "features" / "indicators" / f"ts_code={code}"
        if not root.exists():
            if format_value == "records":
                return _ok([], total=0, indicators=selected_indicators, missing_indicators=missing_indicators)
            return _ok(
                {
                    "ts_code": code,
                    "start_date": start,
                    "end_date": end,
                    "indicators": selected_indicators,
                    "by_date": {},
                },
                total=0,
                missing_indicators=missing_indicators,
            )

        part_glob = str(root / "year=*" / "part-*.parquet")
        selected_columns = ["ts_code", "trade_date", *selected_indicators]
        query = [f"SELECT {', '.join(selected_columns)} FROM read_parquet(?, union_by_name=true) WHERE ts_code = ?"]
        params: list[Any] = [part_glob, code]
        if start:
            query.append("AND trade_date >= ?")
            params.append(start)
        if end:
            query.append("AND trade_date <= ?")
            params.append(end)
        query.append("ORDER BY trade_date")
        rows = _to_records(_safe_fetch_df(" ".join(query), params))
        if format_value == "records":
            return _ok(
                rows,
                total=len(rows),
                indicators=selected_indicators,
                missing_indicators=missing_indicators,
            )

        by_date: dict[str, dict[str, Any]] = {}
        for row in rows:
            trade_date = str(row.get("trade_date") or "").strip()
            if not trade_date:
                continue
            by_date[trade_date] = {name: row.get(name) for name in selected_indicators}

        return _ok(
            {
                "ts_code": code,
                "start_date": start,
                "end_date": end,
                "indicators": selected_indicators,
                "by_date": by_date,
            },
            total=len(by_date),
            missing_indicators=missing_indicators,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/industry/shenwan/tree")
def shenwan_tree(
    level: int | None = Query(default=None, ge=1, le=3),
    version: str | None = Query(default=None),
) -> dict[str, Any]:
    target_version = version
    if not target_version:
        versions = list_shenwan_versions()
        target_version = sorted(versions)[-1] if versions else None
    rows = list_shenwan_industry(version=target_version, level=level)
    if level is not None:
        return _ok(rows, total=len(rows), version=target_version)

    nodes: dict[str, dict[str, Any]] = {}
    for row in rows:
        item = dict(row)
        item.setdefault("children", [])
        code = str(item.get("industry_code") or "")
        if code:
            nodes[code] = item

    roots: list[dict[str, Any]] = []
    for code, node in nodes.items():
        parent_code = str(node.get("parent_code") or "")
        parent = nodes.get(parent_code)
        if parent:
            parent.setdefault("children", []).append(node)
        else:
            roots.append(node)

    for node in nodes.values():
        node["children"] = sorted(
            node.get("children", []),
            key=lambda x: (int(x.get("level") or 99), str(x.get("industry_code") or "")),
        )
    roots = sorted(roots, key=lambda x: (int(x.get("level") or 99), str(x.get("industry_code") or "")))
    return _ok(roots, total=len(roots), version=target_version)


@router.get("/industry/shenwan/members")
def shenwan_members(
    industry_code: str | None = Query(default=None),
    level: int | None = Query(default=None, ge=1, le=3),
    is_new: bool | None = Query(default=True),
    ts_code: str | None = Query(default=None),
    version: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=200, ge=1, le=2000),
) -> dict[str, Any]:
    try:
        target_version = version
        if not target_version:
            versions = list_shenwan_versions()
            target_version = sorted(versions)[-1] if versions else None

        kwargs: dict[str, Any] = {
            "ts_code": _normalize_ts_code(ts_code) if ts_code else None,
            "is_new": None if is_new is None else ("Y" if is_new else "N"),
            "version": target_version,
            "page": page,
            "page_size": page_size,
        }

        if industry_code:
            industry = get_shenwan_by_industry_code(industry_code, version=target_version) or get_shenwan_by_index_code(
                industry_code, version=target_version
            )
            if not industry:
                return _ok([], total=0, page=page, page_size=page_size)
            idx_code = industry.get("index_code")
            level_value = int(industry.get("level") or 0)
            if level_value == 1:
                kwargs["l1_code"] = idx_code
            elif level_value == 2:
                kwargs["l2_code"] = idx_code
            else:
                kwargs["l3_code"] = idx_code
        elif level is not None:
            if level == 1:
                kwargs["l1_code"] = kwargs.get("l1_code")
            elif level == 2:
                kwargs["l2_code"] = kwargs.get("l2_code")
            elif level == 3:
                kwargs["l3_code"] = kwargs.get("l3_code")

        items, total = list_shenwan_members(**kwargs)
        return _ok(items, total=total, page=page, page_size=page_size)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/industry/shenwan/daily")
def shenwan_daily(
    trade_date: str | None = Query(default=None),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    level: int = Query(default=1, ge=1, le=3),
    industry_code: str | None = Query(default=None),
    order_by: str = Query(default="rank"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=300, ge=1, le=2000),
) -> dict[str, Any]:
    try:
        query: dict[str, Any] = {"level": level}
        date_value = _normalize_date(trade_date)
        start = _normalize_date(start_date)
        end = _normalize_date(end_date)

        if date_value:
            query["trade_date"] = date_value
        elif start or end:
            date_range: dict[str, Any] = {}
            if start:
                date_range["$gte"] = start
            if end:
                date_range["$lte"] = end
            query["trade_date"] = date_range
        else:
            latest = list_latest_trade_dates(limit=1, level=level)
            if latest:
                date_value = latest[0]
                query["trade_date"] = date_value

        if industry_code:
            industry = get_shenwan_by_industry_code(industry_code) or get_shenwan_by_index_code(industry_code)
            if industry and industry.get("index_code"):
                query["ts_code"] = industry.get("index_code")

        collection = get_collection("shenwan_daily")
        total = int(collection.count_documents(query))
        sort_key = "pct_change" if str(order_by or "").lower() == "pct_change" else "rank"
        direction = DESCENDING if sort_key == "pct_change" else ASCENDING
        size = max(1, min(page_size, 2000))
        offset = max(page - 1, 0) * size
        items = list(
            collection.find(query, {"_id": 0})
            .sort([(sort_key, direction), ("ts_code", ASCENDING)])
            .skip(offset)
            .limit(size)
        )
        return _ok(items, total=total, page=page, page_size=page_size, trade_date=date_value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/industry/shenwan/daily/ranking")
def shenwan_daily_ranking(
    trade_date: str | None = Query(default=None),
    period: str = Query(default="1d"),
) -> dict[str, Any]:
    try:
        period_map = {"1d": 1, "5d": 5, "10d": 10, "20d": 20, "60d": 60}
        period_value = str(period or "1d").lower()
        if period_value not in period_map:
            raise ValueError("period must be one of: 1d/5d/10d/20d/60d")

        days = period_map[period_value]
        dates = list_latest_trade_dates(limit=days, before_or_on=_normalize_date(trade_date), level=1)
        if not dates:
            return _ok([], trade_date=None, period=period_value)

        latest = dates[0]
        collection = get_collection("shenwan_daily")

        if days == 1:
            rows = list(
                collection.find(
                    {"trade_date": latest, "level": 1},
                    {
                        "_id": 0,
                        "ts_code": 1,
                        "trade_date": 1,
                        "name": 1,
                        "pct_change": 1,
                        "vol": 1,
                        "amount": 1,
                        "rank": 1,
                        "rank_total": 1,
                    },
                ).sort([("pct_change", DESCENDING), ("ts_code", ASCENDING)])
            )
            total = len(rows)
            for idx, row in enumerate(rows, start=1):
                row["rank"] = idx
                row["rank_total"] = total
                row["period"] = period_value
                row["period_pct_change"] = row.get("pct_change")
            return _ok(rows, trade_date=latest, period=period_value)

        pipeline = [
            {"$match": {"trade_date": {"$in": dates}, "level": 1}},
            {
                "$group": {
                    "_id": {"ts_code": "$ts_code", "name": "$name"},
                    "period_pct_change": {"$sum": "$pct_change"},
                    "vol": {"$sum": "$vol"},
                    "amount": {"$sum": "$amount"},
                }
            },
            {"$sort": {"period_pct_change": -1, "_id.ts_code": 1}},
        ]
        rows = list(collection.aggregate(pipeline))
        items: list[dict[str, Any]] = []
        total = len(rows)
        for idx, row in enumerate(rows, start=1):
            ident = row.get("_id") or {}
            items.append(
                {
                    "ts_code": ident.get("ts_code"),
                    "name": ident.get("name"),
                    "trade_date": latest,
                    "period": period_value,
                    "period_pct_change": row.get("period_pct_change"),
                    "vol": row.get("vol"),
                    "amount": row.get("amount"),
                    "rank": idx,
                    "rank_total": total,
                }
            )
        return _ok(items, trade_date=latest, period=period_value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/industry/citic/tree")
def citic_tree(level: int | None = Query(default=None, ge=1, le=3)) -> dict[str, Any]:
    items = list_citic_industry(level=level)
    return _ok(items, total=len(items))


@router.get("/industry/citic/members")
def citic_members(
    industry_code: str | None = Query(default=None),
    level: int | None = Query(default=None, ge=1, le=3),
    is_new: bool | None = Query(default=True),
    ts_code: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=200, ge=1, le=2000),
) -> dict[str, Any]:
    try:
        index_code = None
        if industry_code:
            code = str(industry_code).strip().upper()
            index_code = code if "." in code else f"{code}.CI"

        items, total = list_citic_members(
            index_code=index_code,
            cons_code=_normalize_ts_code(ts_code) if ts_code else None,
            level=level,
            is_new=None if is_new is None else ("Y" if is_new else "N"),
            page=page,
            page_size=page_size,
        )
        return _ok(items, total=total, page=page, page_size=page_size)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/industry/citic/daily")
def citic_daily(
    trade_date: str | None = Query(default=None),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    level: int = Query(default=1, ge=1, le=3),
    industry_code: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=300, ge=1, le=2000),
) -> dict[str, Any]:
    try:
        query: dict[str, Any] = {"level": level}
        date_value = _normalize_date(trade_date)
        start = _normalize_date(start_date)
        end = _normalize_date(end_date)

        if date_value:
            query["trade_date"] = date_value
        elif start or end:
            date_range: dict[str, Any] = {}
            if start:
                date_range["$gte"] = start
            if end:
                date_range["$lte"] = end
            query["trade_date"] = date_range
        else:
            latest = list_latest_citic_trade_dates(limit=1, level=level)
            if latest:
                date_value = latest[0]
                query["trade_date"] = date_value

        if industry_code:
            code = str(industry_code).strip().upper()
            if "." not in code:
                code = f"{code}.CI"
            query["ts_code"] = code

        collection = get_collection("citic_daily")
        total = int(collection.count_documents(query))
        size = max(1, min(page_size, 2000))
        offset = max(page - 1, 0) * size
        items = list(
            collection.find(query, {"_id": 0})
            .sort([("pct_change", DESCENDING), ("ts_code", ASCENDING)])
            .skip(offset)
            .limit(size)
        )
        return _ok(items, total=total, page=page, page_size=page_size, trade_date=date_value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/market-index/daily-basic")
def market_index_daily_basic(
    ts_codes: str | None = Query(default=None),
    trade_date: str | None = Query(default=None),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=500, ge=1, le=5000),
) -> dict[str, Any]:
    try:
        query: dict[str, Any] = {}
        date_value = _normalize_date(trade_date)
        start = _normalize_date(start_date)
        end = _normalize_date(end_date)

        if date_value:
            query["trade_date"] = date_value
        elif start or end:
            date_range: dict[str, Any] = {}
            if start:
                date_range["$gte"] = start
            if end:
                date_range["$lte"] = end
            query["trade_date"] = date_range
        else:
            latest = list_market_trade_dates(limit=1)
            if latest:
                date_value = latest[0]
                query["trade_date"] = date_value

        codes = _normalize_ts_codes(ts_codes)
        if codes:
            query["ts_code"] = {"$in": codes}

        collection = get_collection("market_index_dailybasic")
        total = int(collection.count_documents(query))
        size = max(1, min(page_size, 5000))
        offset = max(page - 1, 0) * size
        items = list(
            collection.find(query, {"_id": 0})
            .sort([("trade_date", DESCENDING), ("ts_code", ASCENDING)])
            .skip(offset)
            .limit(size)
        )
        return _ok(items, total=total, page=page, page_size=page_size, trade_date=date_value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/trade-calendar")
def trade_calendar(
    exchange: str = Query(default="SSE"),
    start_date: str = Query(...),
    end_date: str = Query(...),
    is_open: bool | None = Query(default=None),
) -> dict[str, Any]:
    try:
        start = _normalize_date(start_date, required=True)
        end = _normalize_date(end_date, required=True)
        if start and end and start > end:
            raise ValueError("start_date cannot be after end_date")
        query: dict[str, Any] = {
            "exchange": str(exchange or "SSE").strip().upper(),
            "cal_date": {"$gte": start, "$lte": end},
        }
        if is_open is not None:
            query["is_open"] = 1 if is_open else 0
        items = list(
            get_collection("trade_calendar")
            .find(query, {"_id": 0, "exchange": 1, "cal_date": 1, "is_open": 1, "pretrade_date": 1})
            .sort("cal_date", ASCENDING)
        )
        return _ok(items, total=len(items))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/trade-calendar/latest-trade-date")
def latest_trade_date(exchange: str = Query(default="SSE")) -> dict[str, Any]:
    date_value = _resolve_latest_trade_date(str(exchange or "SSE").strip().upper())
    return _ok({"trade_date": date_value})


@router.get("/stocks/{ts_code}/limit-prices")
def stock_limit_prices(
    ts_code: str,
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
) -> dict[str, Any]:
    try:
        code = _normalize_ts_code(ts_code)
        start = _normalize_date(start_date)
        end = _normalize_date(end_date)
        root = settings.data_dir / "raw" / "daily_limit" / f"ts_code={code}"
        if not root.exists():
            return _ok([])
        part_glob = str(root / "year=*" / "part-*.parquet")
        query = [
            "SELECT ts_code, trade_date, pre_close, up_limit, down_limit",
            "FROM read_parquet(?, union_by_name=true)",
            "WHERE ts_code = ?",
        ]
        params: list[Any] = [part_glob, code]
        if start:
            query.append("AND trade_date >= ?")
            params.append(start)
        if end:
            query.append("AND trade_date <= ?")
            params.append(end)
        query.append("ORDER BY trade_date")
        rows = _to_records(_safe_fetch_df(" ".join(query), params))
        return _ok(rows)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/stocks/limit-prices/snapshot")
def limit_prices_snapshot(
    trade_date: str | None = Query(default=None),
    ts_codes: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=500, ge=1, le=5000),
) -> dict[str, Any]:
    try:
        date_value = _normalize_date(trade_date)
        if not date_value:
            date_value = _latest_trade_date_from_parquet("raw/daily_limit")
        if not date_value:
            return _ok([], total=0, trade_date=None)

        year = date_value[:4]
        part_glob = str(settings.data_dir / "raw" / "daily_limit" / "ts_code=*" / f"year={year}" / "part-*.parquet")
        query = [
            "SELECT ts_code, trade_date, pre_close, up_limit, down_limit",
            "FROM read_parquet(?, hive_partitioning=1, union_by_name=true)",
            "WHERE trade_date = ?",
        ]
        params: list[Any] = [part_glob, date_value]
        codes = _normalize_ts_codes(ts_codes)
        if codes:
            placeholders = ", ".join(["?"] * len(codes))
            query.append(f"AND ts_code IN ({placeholders})")
            params.extend(codes)
        query.append("ORDER BY ts_code")
        rows = _to_records(_safe_fetch_df(" ".join(query), params))
        paged, total = _paginate(rows, page=page, page_size=page_size)
        return _ok(paged, total=total, trade_date=date_value, page=page, page_size=page_size)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/stocks/{ts_code}/financials/indicators")
def financial_indicators(
    ts_code: str,
    period: str | None = Query(default=None),
    period_type: str = Query(default="quarterly"),
    limit: int = Query(default=8, ge=1, le=40),
) -> dict[str, Any]:
    try:
        code = _normalize_ts_code(ts_code)
        query: dict[str, Any] = {"ts_code": code}
        period_value = _normalize_date(period)
        if period_value:
            query["end_date"] = period_value
        if str(period_type or "quarterly").lower() == "annual":
            query["end_date"] = {"$regex": r"1231$"}

        items = list(
            get_collection("financial_indicators")
            .find(query, {"_id": 0})
            .sort([("end_date", DESCENDING), ("ann_date", DESCENDING)])
            .limit(limit)
        )
        return _ok(items, total=len(items))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/stocks/{ts_code}/financials/income")
def financial_income(
    ts_code: str,
    period: str | None = Query(default=None),
    limit: int = Query(default=8, ge=1, le=40),
) -> dict[str, Any]:
    try:
        code = _normalize_ts_code(ts_code)
        query: dict[str, Any] = {"ts_code": code}
        period_value = _normalize_date(period)
        if period_value:
            query["end_date"] = period_value
        items = list(
            get_collection("income_statement")
            .find(query, {"_id": 0})
            .sort([("end_date", DESCENDING), ("ann_date", DESCENDING)])
            .limit(limit)
        )
        return _ok(items, total=len(items))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/stocks/{ts_code}/financials/balance")
def financial_balance(
    ts_code: str,
    period: str | None = Query(default=None),
    limit: int = Query(default=8, ge=1, le=40),
) -> dict[str, Any]:
    try:
        code = _normalize_ts_code(ts_code)
        query: dict[str, Any] = {"ts_code": code}
        period_value = _normalize_date(period)
        if period_value:
            query["end_date"] = period_value
        items = list(
            get_collection("balance_sheet")
            .find(query, {"_id": 0})
            .sort([("end_date", DESCENDING), ("ann_date", DESCENDING)])
            .limit(limit)
        )
        return _ok(items, total=len(items))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/stocks/{ts_code}/financials/cashflow")
def financial_cashflow(
    ts_code: str,
    period: str | None = Query(default=None),
    limit: int = Query(default=8, ge=1, le=40),
) -> dict[str, Any]:
    try:
        code = _normalize_ts_code(ts_code)
        query: dict[str, Any] = {"ts_code": code}
        period_value = _normalize_date(period)
        if period_value:
            query["end_date"] = period_value
        items = list(
            get_collection("cashflow")
            .find(query, {"_id": 0})
            .sort([("end_date", DESCENDING), ("ann_date", DESCENDING)])
            .limit(limit)
        )
        return _ok(items, total=len(items))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/stocks/financials/indicators/batch")
def financial_indicators_batch(payload: FinancialIndicatorsBatchRequest) -> dict[str, Any]:
    try:
        codes = _normalize_ts_codes(payload.ts_codes)
        if not codes:
            return _ok([])
        query: dict[str, Any] = {"ts_code": {"$in": codes}}
        period_value = _normalize_date(payload.period)
        if period_value:
            query["end_date"] = period_value

        rows = list(
            get_collection("financial_indicators")
            .find(query, {"_id": 0})
            .sort([("end_date", DESCENDING), ("ts_code", ASCENDING)])
        )
        latest_by_code: dict[str, dict[str, Any]] = {}
        for row in rows:
            code = str(row.get("ts_code") or "").upper()
            if code and code not in latest_by_code:
                latest_by_code[code] = row
        items = [latest_by_code[code] for code in codes if code in latest_by_code]
        items = _apply_fields(items, fields=payload.fields, always_keep={"ts_code", "end_date", "ann_date"})
        return _ok(items, total=len(items))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/stocks/financials/indicators/screen")
def financial_indicators_screen(
    period: str | None = Query(default=None),
    roe_min: float | None = Query(default=None),
    revenue_yoy_min: float | None = Query(default=None),
    n_income_yoy_min: float | None = Query(default=None),
    debt_to_assets_max: float | None = Query(default=None),
    netprofit_margin_min: float | None = Query(default=None),
    fcf_positive: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=200, ge=1, le=2000),
) -> dict[str, Any]:
    try:
        query: dict[str, Any] = {}
        period_value = _normalize_date(period)
        if period_value:
            query["end_date"] = period_value
        if roe_min is not None:
            query["roe"] = {"$gte": float(roe_min)}
        if revenue_yoy_min is not None:
            query["revenue_yoy"] = {"$gte": float(revenue_yoy_min)}
        if n_income_yoy_min is not None:
            query["n_income_yoy"] = {"$gte": float(n_income_yoy_min)}
        if debt_to_assets_max is not None:
            query["debt_to_assets"] = {"$lte": float(debt_to_assets_max)}
        if netprofit_margin_min is not None:
            query["netprofit_margin"] = {"$gte": float(netprofit_margin_min)}
        if fcf_positive is True:
            query["fcf"] = {"$gt": 0}
        elif fcf_positive is False:
            query["fcf"] = {"$lte": 0}

        collection = get_collection("financial_indicators")
        total = int(collection.count_documents(query))
        size = max(1, min(page_size, 2000))
        offset = max(page - 1, 0) * size
        items = list(
            collection.find(query, {"_id": 0})
            .sort([("end_date", DESCENDING), ("roe", DESCENDING), ("ts_code", ASCENDING)])
            .skip(offset)
            .limit(size)
        )
        return _ok(items, total=total, page=page, page_size=page_size)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/stocks/{ts_code}/dividends")
def stock_dividends(
    ts_code: str,
    limit: int = Query(default=200, ge=1, le=500),
) -> dict[str, Any]:
    try:
        code = _normalize_ts_code(ts_code)
        items = list(
            get_collection("dividend_history")
            .find({"ts_code": code}, {"_id": 0})
            .sort([("end_date", DESCENDING), ("ann_date", DESCENDING)])
            .limit(limit)
        )
        return _ok(items, total=len(items))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/stocks/{ts_code}/dividends/summary")
def stock_dividends_summary(ts_code: str) -> dict[str, Any]:
    try:
        code = _normalize_ts_code(ts_code)
        rows = list(
            get_collection("dividend_history")
            .find({"ts_code": code}, {"_id": 0})
            .sort([("end_date", DESCENDING), ("ann_date", DESCENDING)])
            .limit(300)
        )
        if not rows:
            return _ok(
                {
                    "ts_code": code,
                    "consecutive_years": 0,
                    "avg_dv_ratio_5y": None,
                    "dividend_cagr_5y": None,
                    "total_cash_div_5y": 0.0,
                    "latest_dv_ratio": None,
                    "payout_ratio": None,
                }
            )

        now_year = dt.datetime.now().year
        recent = []
        for row in rows:
            end_date = str(row.get("end_date") or "")
            if len(end_date) >= 4 and end_date[:4].isdigit() and int(end_date[:4]) >= now_year - 5:
                recent.append(row)

        years = sorted(
            {int(str(row.get("end_date") or "")[:4]) for row in recent if str(row.get("end_date") or "")[:4].isdigit()},
            reverse=True,
        )
        consecutive = 0
        if years:
            expect = years[0]
            for year in years:
                if year == expect:
                    consecutive += 1
                    expect -= 1
                else:
                    break

        dv_values = [float(row["dv_ratio"]) for row in recent if isinstance(row.get("dv_ratio"), (int, float))]
        cash_values = [float(row["cash_div"]) for row in recent if isinstance(row.get("cash_div"), (int, float))]
        latest = rows[0]
        return _ok(
            {
                "ts_code": code,
                "consecutive_years": consecutive,
                "avg_dv_ratio_5y": (sum(dv_values) / len(dv_values)) if dv_values else None,
                "dividend_cagr_5y": None,
                "total_cash_div_5y": sum(cash_values) if cash_values else 0.0,
                "latest_dv_ratio": latest.get("dv_ratio"),
                "payout_ratio": latest.get("payout_ratio"),
            }
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/stocks/dividends/screen")
def dividends_screen(
    dv_ratio_min: float | None = Query(default=None),
    consecutive_years_min: int | None = Query(default=None),
    payout_ratio_max: float | None = Query(default=None),
    total_mv_min: float | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=200, ge=1, le=2000),
) -> dict[str, Any]:
    query: dict[str, Any] = {}
    if dv_ratio_min is not None:
        query["dv_ratio"] = {"$gte": float(dv_ratio_min)}
    if consecutive_years_min is not None:
        query["consecutive_years"] = {"$gte": int(consecutive_years_min)}
    if payout_ratio_max is not None:
        query["payout_ratio"] = {"$lte": float(payout_ratio_max)}
    if total_mv_min is not None:
        query["total_mv"] = {"$gte": float(total_mv_min)}

    collection = get_collection("dividend_history")
    total = int(collection.count_documents(query))
    size = max(1, min(page_size, 2000))
    offset = max(page - 1, 0) * size
    items = list(
        collection.find(query, {"_id": 0})
        .sort([("dv_ratio", DESCENDING), ("end_date", DESCENDING), ("ts_code", ASCENDING)])
        .skip(offset)
        .limit(size)
    )
    return _ok(items, total=total, page=page, page_size=page_size)


@router.get("/stocks/{ts_code}/insider-trades")
def stock_insider_trades(
    ts_code: str,
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    holder_type: str | None = Query(default=None),
    trade_type: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=200, ge=1, le=2000),
) -> dict[str, Any]:
    try:
        code = _normalize_ts_code(ts_code)
        query: dict[str, Any] = {"ts_code": code}
        start = _normalize_date(start_date)
        end = _normalize_date(end_date)
        if start or end:
            date_range: dict[str, Any] = {}
            if start:
                date_range["$gte"] = start
            if end:
                date_range["$lte"] = end
            query["ann_date"] = date_range
        if holder_type:
            query["holder_type"] = str(holder_type).strip().upper()
        if trade_type:
            query["in_de"] = str(trade_type).strip().upper()

        collection = get_collection("insider_trades")
        total = int(collection.count_documents(query))
        size = max(1, min(page_size, 2000))
        offset = max(page - 1, 0) * size
        items = list(
            collection.find(query, {"_id": 0})
            .sort([("ann_date", DESCENDING), ("ts_code", ASCENDING)])
            .skip(offset)
            .limit(size)
        )
        return _ok(items, total=total, page=page, page_size=page_size)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/market/insider-trades/latest")
def market_insider_trades_latest(
    trade_type: str | None = Query(default=None),
    days: int = Query(default=30, ge=1, le=365),
    min_amount: float | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=200, ge=1, le=2000),
) -> dict[str, Any]:
    query: dict[str, Any] = {}
    if trade_type:
        query["in_de"] = str(trade_type).strip().upper()
    if min_amount is not None:
        query["amount"] = {"$gte": float(min_amount)}

    latest = _latest_trade_date_from_collection("insider_trades", field="ann_date")
    if latest:
        start_dt = dt.datetime.strptime(latest, "%Y%m%d") - dt.timedelta(days=max(days - 1, 0))
        query["ann_date"] = {"$gte": start_dt.strftime("%Y%m%d"), "$lte": latest}

    collection = get_collection("insider_trades")
    total = int(collection.count_documents(query))
    size = max(1, min(page_size, 2000))
    offset = max(page - 1, 0) * size
    items = list(
        collection.find(query, {"_id": 0})
        .sort([("ann_date", DESCENDING), ("amount", DESCENDING), ("ts_code", ASCENDING)])
        .skip(offset)
        .limit(size)
    )
    return _ok(items, total=total, page=page, page_size=page_size)


def _query_macro(indicator: str, *, start_date: str | None, end_date: str | None, limit: int) -> list[dict[str, Any]]:
    query: dict[str, Any] = {"indicator": indicator}
    start = _normalize_date(start_date)
    end = _normalize_date(end_date)
    if start or end:
        date_range: dict[str, Any] = {}
        if start:
            date_range["$gte"] = start
        if end:
            date_range["$lte"] = end
        query["date"] = date_range
    return list(
        get_collection("macro_indicators")
        .find(query, {"_id": 0})
        .sort([("date", DESCENDING)])
        .limit(max(1, min(limit, 500)))
    )


@router.get("/macro/money-supply")
def macro_money_supply(
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    limit: int = Query(default=120, ge=1, le=500),
) -> dict[str, Any]:
    try:
        return _ok(_query_macro("money_supply", start_date=start_date, end_date=end_date, limit=limit))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/macro/lpr")
def macro_lpr(
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    limit: int = Query(default=120, ge=1, le=500),
) -> dict[str, Any]:
    try:
        return _ok(_query_macro("lpr", start_date=start_date, end_date=end_date, limit=limit))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/macro/pmi")
def macro_pmi(
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    limit: int = Query(default=120, ge=1, le=500),
) -> dict[str, Any]:
    try:
        return _ok(_query_macro("pmi", start_date=start_date, end_date=end_date, limit=limit))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/macro/cpi-ppi")
def macro_cpi_ppi(
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    limit: int = Query(default=120, ge=1, le=500),
) -> dict[str, Any]:
    try:
        return _ok(_query_macro("cpi_ppi", start_date=start_date, end_date=end_date, limit=limit))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/macro/social-financing")
def macro_social_financing(
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    limit: int = Query(default=120, ge=1, le=500),
) -> dict[str, Any]:
    try:
        return _ok(_query_macro("social_financing", start_date=start_date, end_date=end_date, limit=limit))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _query_events(
    event_type: str,
    *,
    ts_code: str | None = None,
    page: int = 1,
    page_size: int = 200,
) -> dict[str, Any]:
    query: dict[str, Any] = {"event_type": event_type}
    if ts_code:
        query["ts_code"] = _normalize_ts_code(ts_code)
    collection = get_collection("corporate_events")
    total = int(collection.count_documents(query))
    size = max(1, min(page_size, 2000))
    offset = max(page - 1, 0) * size
    items = list(
        collection.find(query, {"_id": 0})
        .sort([("ann_date", DESCENDING), ("ts_code", ASCENDING)])
        .skip(offset)
        .limit(size)
    )
    return _ok(items, total=total, page=page, page_size=page_size)


@router.get("/stocks/{ts_code}/events/buyback")
def stock_event_buyback(
    ts_code: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=200, ge=1, le=2000),
) -> dict[str, Any]:
    try:
        return _query_events("buyback", ts_code=ts_code, page=page, page_size=page_size)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/market/events/ma-restructure")
def market_event_ma_restructure(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=200, ge=1, le=2000),
) -> dict[str, Any]:
    return _query_events("ma_restructure", page=page, page_size=page_size)


@router.get("/stocks/{ts_code}/events/holder-changes")
def stock_event_holder_changes(
    ts_code: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=200, ge=1, le=2000),
) -> dict[str, Any]:
    try:
        return _query_events("holder_changes", ts_code=ts_code, page=page, page_size=page_size)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
