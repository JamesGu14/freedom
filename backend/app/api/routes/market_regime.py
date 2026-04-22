from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from app.data.mongo_market_regime import (
    get_latest_market_regime,
    get_market_regime_by_date,
    get_market_regime_history,
)

router = APIRouter()


@router.get("/market-regime/latest")
def get_latest_regime_route() -> dict[str, Any]:
    doc = get_latest_market_regime()
    return doc or {}


@router.get("/market-regime/by-date")
def get_regime_by_date_route(trade_date: str = Query(...)) -> dict[str, Any]:
    doc = get_market_regime_by_date(trade_date)
    return doc or {}


@router.get("/market-regime/history")
def get_regime_history_route(limit: int = Query(default=60, ge=1, le=2000)) -> dict[str, Any]:
    items = get_market_regime_history(limit=limit)
    return {"items": items, "total": len(items)}
