from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.deps import get_current_user
from app.services.backtest_service import (
    compare_backtests,
    create_backtest_run_meta,
    delete_backtest_run_meta,
    get_backtest_detail,
    get_backtest_drawdown,
    get_backtest_holdings_summary,
    get_backtest_nav,
    get_backtest_positions,
    get_backtest_signals,
    get_backtest_trades_by_code,
    get_backtest_trades,
    list_backtests,
)

router = APIRouter()


class BacktestCreateRequest(BaseModel):
    strategy_id: str = Field(min_length=1)
    strategy_version_id: str = Field(min_length=1)
    start_date: str = Field(min_length=8)
    end_date: str = Field(min_length=8)
    run_type: str = Field(default="range")
    initial_capital: float = Field(default=1_000_000.0, gt=0)
    run_id: str | None = None


class BacktestCompareRequest(BaseModel):
    run_ids: list[str] = Field(min_length=2, max_length=5)


@router.post("/backtests")
def create_backtest(
    payload: BacktestCreateRequest,
    current_user: dict[str, object] = Depends(get_current_user),
) -> dict[str, Any]:
    username = str(current_user.get("username") or "")
    try:
        item = create_backtest_run_meta(
            strategy_id=payload.strategy_id,
            strategy_version_id=payload.strategy_version_id,
            start_date=payload.start_date,
            end_date=payload.end_date,
            run_type=payload.run_type,
            initial_capital=payload.initial_capital,
            created_by=username,
            run_id=payload.run_id,
        )
    except ValueError as exc:
        detail = str(exc)
        if "not found" in detail:
            raise HTTPException(status_code=404, detail=detail) from exc
        raise HTTPException(status_code=400, detail=detail) from exc
    return item


@router.get("/backtests")
def list_backtest_items(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    strategy_id: str | None = Query(default=None),
    strategy_version_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
) -> dict[str, Any]:
    items, total = list_backtests(
        page=page,
        page_size=page_size,
        strategy_id=strategy_id,
        strategy_version_id=strategy_version_id,
        status=status,
    )
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/backtests/compare")
def compare_backtest_items(payload: BacktestCompareRequest) -> dict[str, Any]:
    run_ids = [str(item).strip() for item in payload.run_ids if str(item).strip()]
    if len(run_ids) < 2 or len(run_ids) > 5:
        raise HTTPException(status_code=400, detail="run_ids length must be 2~5")
    items = compare_backtests(run_ids)
    return {"items": items, "total": len(items)}


@router.get("/backtests/{run_id}")
def get_backtest(run_id: str) -> dict[str, Any]:
    item = get_backtest_detail(run_id)
    if not item:
        raise HTTPException(status_code=404, detail="run not found")
    return item


@router.delete("/backtests/{run_id}")
def delete_backtest(run_id: str) -> dict[str, Any]:
    try:
        deleted = delete_backtest_run_meta(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="run not found")
    return {"run_id": run_id, "deleted": True}


@router.get("/backtests/{run_id}/nav")
def get_backtest_nav_items(run_id: str) -> dict[str, Any]:
    run = get_backtest_detail(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    items = get_backtest_nav(run_id)
    return {"run_id": run_id, "items": items, "total": len(items)}


@router.get("/backtests/{run_id}/drawdown")
def get_backtest_drawdown_items(run_id: str) -> dict[str, Any]:
    run = get_backtest_detail(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    items = get_backtest_drawdown(run_id)
    return {"run_id": run_id, "items": items, "total": len(items)}


@router.get("/backtests/{run_id}/trades")
def list_backtest_trade_items(
    run_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    ts_code: str | None = Query(default=None),
) -> dict[str, Any]:
    run = get_backtest_detail(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    items, total = get_backtest_trades(
        run_id=run_id,
        page=page,
        page_size=page_size,
        ts_code=ts_code,
    )
    return {
        "run_id": run_id,
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/backtests/{run_id}/trades-by-code")
def list_backtest_trade_items_by_code(
    run_id: str,
    ts_code: str = Query(min_length=6),
    limit: int = Query(default=5000, ge=1, le=20000),
) -> dict[str, Any]:
    run = get_backtest_detail(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    items = get_backtest_trades_by_code(run_id=run_id, ts_code=ts_code, limit=limit)
    return {"run_id": run_id, "items": items, "total": len(items)}


@router.get("/backtests/{run_id}/positions")
def list_backtest_position_items(
    run_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    trade_date: str | None = Query(default=None),
) -> dict[str, Any]:
    run = get_backtest_detail(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    items, total = get_backtest_positions(
        run_id=run_id,
        page=page,
        page_size=page_size,
        trade_date=trade_date,
    )
    return {
        "run_id": run_id,
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/backtests/{run_id}/signals")
def list_backtest_signal_items(
    run_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    trade_date: str | None = Query(default=None),
) -> dict[str, Any]:
    run = get_backtest_detail(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    items, total = get_backtest_signals(
        run_id=run_id,
        page=page,
        page_size=page_size,
        trade_date=trade_date,
    )
    return {
        "run_id": run_id,
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/backtests/{run_id}/holdings-summary")
def get_backtest_holdings_summary_items(run_id: str) -> dict[str, Any]:
    run = get_backtest_detail(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    items = get_backtest_holdings_summary(run_id)
    return {"run_id": run_id, "items": items, "total": len(items)}
