from __future__ import annotations

from fastapi import APIRouter, Query

from app.data.mongo_market_index import (
    DEFAULT_MARKET_INDEX_CODES,
    get_market_index_chart,
    get_market_index_factors,
    get_market_index_overview,
    get_market_index_series,
    list_market_trade_dates,
)

router = APIRouter()


def _parse_codes(value: str | None) -> list[str]:
    if not value:
        return list(DEFAULT_MARKET_INDEX_CODES)
    parts = [item.strip().upper() for item in value.split(",")]
    items = [item for item in parts if item]
    return list(dict.fromkeys(items)) or list(DEFAULT_MARKET_INDEX_CODES)


@router.get("/market-index/dates")
def get_market_index_dates(
    limit: int = Query(default=30, ge=1, le=300),
) -> dict[str, object]:
    items = list_market_trade_dates(limit=limit)
    return {"items": items, "total": len(items)}


@router.get("/market-index/overview")
def get_market_overview(
    trade_date: str | None = Query(default=None),
    index_codes: str | None = Query(default=None),
) -> dict[str, object]:
    codes = _parse_codes(index_codes)
    items = get_market_index_overview(trade_date=trade_date, index_codes=codes)
    return {"trade_date": trade_date, "index_codes": codes, "items": items, "total": len(items)}


@router.get("/market-index/series")
def get_market_series(
    ts_code: str = Query(...),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    limit: int = Query(default=240, ge=1, le=2000),
) -> dict[str, object]:
    rows = get_market_index_series(
        ts_code=ts_code.upper(),
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )
    return {"ts_code": ts_code.upper(), "items": rows, "total": len(rows)}


@router.get("/market-index/factors")
def get_market_factors(
    ts_code: str = Query(...),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    limit: int = Query(default=120, ge=1, le=2000),
) -> dict[str, object]:
    rows = get_market_index_factors(
        ts_code=ts_code.upper(),
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )
    return {"ts_code": ts_code.upper(), "items": rows, "total": len(rows)}


@router.get("/market-index/chart")
def get_market_chart(
    ts_code: str = Query(...),
    limit: int = Query(default=500, ge=1, le=2000),
) -> dict[str, object]:
    code = ts_code.upper()
    rows = get_market_index_chart(ts_code=code, limit=limit)
    return {"ts_code": code, "items": rows, "total": len(rows)}
