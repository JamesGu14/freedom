from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from app.core.cache import cache_delete_pattern
from app.data.mongo_daily_stock_signals import update_stock_resonance_state
from app.services.daily_stock_signals_service import (
    get_daily_stock_signal_by_type,
    get_daily_stock_signals_overview,
    get_signal_statistics,
    get_stock_pattern_details,
    get_stock_recent_signals,
    list_available_daily_stock_signal_dates,
)

router = APIRouter()


class ResonanceStatePayload(BaseModel):
    trade_date: str = Field(..., min_length=8, max_length=8)
    ts_code: str = Field(..., min_length=1, max_length=32)
    signal_side: str = Field(..., pattern="^(buy|sell)$")
    resonance_level: str = Field(..., pattern="^(very_strong|strong|normal)$")
    user_state: str | None = Field(default=None)

    @field_validator("user_state")
    @classmethod
    def validate_user_state(cls, v: str | None) -> str | None:
        if v is not None and v not in ("acknowledged", "ignored"):
            raise ValueError('user_state must be "acknowledged", "ignored", or null')
        return v


@router.get("/daily-stock-signals/dates")
def list_daily_stock_signal_dates_route(limit: int = Query(default=365, ge=1, le=2000)) -> dict[str, Any]:
    items = list_available_daily_stock_signal_dates(limit=limit)
    return {"items": items, "total": len(items)}


@router.get("/daily-stock-signals/overview")
def get_daily_stock_signal_overview_route(
    trade_date: str | None = Query(default=None),
    top_n: int = Query(default=50, ge=1, le=500),
) -> dict[str, Any]:
    return get_daily_stock_signals_overview(trade_date=trade_date, top_n=top_n)


@router.get("/daily-stock-signals/by-type")
def get_daily_stock_signal_by_type_route(
    trade_date: str = Query(...),
    signal_type: str = Query(...),
) -> dict[str, Any]:
    item = get_daily_stock_signal_by_type(trade_date=trade_date, signal_type=signal_type)
    if not item:
        raise HTTPException(status_code=404, detail="signal group not found")
    return item


@router.get("/daily-stock-signals/stock/{ts_code}")
def get_stock_signals_route(
    ts_code: str,
    limit_days: int = Query(default=30, ge=1, le=365),
) -> dict[str, Any]:
    signals = get_stock_recent_signals(ts_code=ts_code, limit_days=limit_days)
    return {"ts_code": ts_code, "signals": signals, "total": len(signals)}


@router.get("/daily-stock-signals/stock/{ts_code}/patterns")
def get_stock_patterns_route(
    ts_code: str,
    trade_date: str = Query(...),
) -> dict[str, Any]:
    details = get_stock_pattern_details(ts_code=ts_code, trade_date=trade_date)
    if not details:
        raise HTTPException(status_code=404, detail="stock pattern details not found")
    return details


@router.get("/daily-stock-signals/statistics")
def get_signal_statistics_route(
    trade_date: str | None = Query(default=None),
) -> dict[str, Any]:
    return get_signal_statistics(trade_date=trade_date)


@router.put("/daily-stock-signals/resonance/state")
def update_resonance_state(payload: ResonanceStatePayload) -> dict[str, object]:
    success = update_stock_resonance_state(
        trade_date=payload.trade_date,
        ts_code=payload.ts_code,
        signal_side=payload.signal_side,
        resonance_level=payload.resonance_level,
        user_state=payload.user_state,
    )

    if not success:
        raise HTTPException(status_code=404, detail="Stock not found in resonance group")

    cache_delete_pattern(f"signals:overview:{payload.trade_date}:*")
    cache_delete_pattern(f"signals:patterns:*:{payload.trade_date}")

    return {
        "success": True,
        "trade_date": payload.trade_date,
        "ts_code": payload.ts_code,
        "user_state": payload.user_state,
    }
