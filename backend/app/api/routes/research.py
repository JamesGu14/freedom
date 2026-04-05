from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.services.research_service import (
    get_market_research_hsgt_flow,
    get_market_research_index_detail,
    get_market_research_indexes,
    get_market_research_sectors,
    get_stock_research_chips,
    get_stock_research_dividends,
    get_stock_research_events,
    get_stock_research_financials,
    get_stock_research_flows,
    get_stock_research_holders,
    get_stock_research_overview,
)

router = APIRouter()


@router.get("/research/stocks/{ts_code}/overview")
def research_stock_overview(ts_code: str) -> dict[str, Any]:
    try:
        return get_stock_research_overview(ts_code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/research/stocks/{ts_code}/financials")
def research_stock_financials(
    ts_code: str,
    limit: int = Query(default=8, ge=1, le=40),
) -> dict[str, Any]:
    try:
        return get_stock_research_financials(ts_code, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/research/stocks/{ts_code}/dividends")
def research_stock_dividends(
    ts_code: str,
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    try:
        return get_stock_research_dividends(ts_code, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/research/stocks/{ts_code}/holders")
def research_stock_holders(
    ts_code: str,
    limit: int = Query(default=24, ge=1, le=120),
) -> dict[str, Any]:
    try:
        return get_stock_research_holders(ts_code, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/research/stocks/{ts_code}/chips")
def research_stock_chips(
    ts_code: str,
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    limit: int = Query(default=120, ge=1, le=500),
) -> dict[str, Any]:
    try:
        return get_stock_research_chips(ts_code, start_date=start_date, end_date=end_date, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/research/stocks/{ts_code}/flows")
def research_stock_flows(
    ts_code: str,
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    limit: int = Query(default=120, ge=1, le=500),
) -> dict[str, Any]:
    try:
        return get_stock_research_flows(ts_code, start_date=start_date, end_date=end_date, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/research/stocks/{ts_code}/events")
def research_stock_events(
    ts_code: str,
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    limit: int = Query(default=120, ge=1, le=500),
) -> dict[str, Any]:
    try:
        return get_stock_research_events(ts_code, start_date=start_date, end_date=end_date, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/research/market/indexes")
def research_market_indexes() -> dict[str, Any]:
    return get_market_research_indexes()


@router.get("/research/market/indexes/{ts_code}")
def research_market_index_detail(
    ts_code: str,
    limit: int = Query(default=240, ge=1, le=1000),
) -> dict[str, Any]:
    try:
        return get_market_research_index_detail(ts_code, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/research/market/sectors")
def research_market_sectors(
    limit: int = Query(default=10, ge=1, le=50),
) -> dict[str, Any]:
    return get_market_research_sectors(limit=limit)


@router.get("/research/market/hsgt-flow")
def research_market_hsgt_flow(
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    limit: int = Query(default=120, ge=1, le=500),
) -> dict[str, Any]:
    try:
        return get_market_research_hsgt_flow(start_date=start_date, end_date=end_date, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
