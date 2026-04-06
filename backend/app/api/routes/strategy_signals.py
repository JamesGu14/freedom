from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from app.services.strategy_signal_service import (
    STRATEGY_PORTFOLIO_ID,
    list_strategy_signal_dates,
    query_latest_signal_date,
    query_strategy_signals,
)

router = APIRouter()


@router.get("/strategy-signals")
def list_signals(
    signal_date: str | None = Query(default=None),
    strategy_version_id: str | None = Query(default=None),
    portfolio_id: str | None = Query(default=None),
    portfolio_type: str | None = Query(default=None),
    signal: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=500),
) -> dict[str, Any]:
    normalized_signal = str(signal or "").strip().upper() or None
    items, total = query_strategy_signals(
        signal_date=signal_date,
        strategy_version_id=strategy_version_id,
        portfolio_id=portfolio_id,
        portfolio_type=portfolio_type,
        signal=normalized_signal,
        page=page,
        page_size=page_size,
    )
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/strategy-signals/latest")
def get_latest_signals(
    strategy_version_id: str | None = Query(default=None),
    portfolio_id: str = Query(default=STRATEGY_PORTFOLIO_ID),
    portfolio_type: str = Query(default="strategy"),
    page_size: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    latest_date = query_latest_signal_date(
        strategy_version_id=strategy_version_id,
        portfolio_id=portfolio_id,
        portfolio_type=portfolio_type,
    )
    if not latest_date:
        return {"signal_date": None, "items": [], "total": 0}
    items, total = query_strategy_signals(
        signal_date=latest_date,
        strategy_version_id=strategy_version_id,
        portfolio_id=portfolio_id,
        portfolio_type=portfolio_type,
        page=1,
        page_size=page_size,
    )
    return {
        "signal_date": latest_date,
        "items": items,
        "total": total,
        "page_size": page_size,
    }


@router.get("/strategy-signals/dates")
def get_signal_dates(
    strategy_version_id: str | None = Query(default=None),
    portfolio_id: str = Query(default=STRATEGY_PORTFOLIO_ID),
    limit: int = Query(default=120, ge=1, le=2000),
) -> dict[str, Any]:
    items = list_strategy_signal_dates(
        strategy_version_id=strategy_version_id,
        portfolio_id=portfolio_id,
        limit=limit,
    )
    return {"items": items, "total": len(items)}

