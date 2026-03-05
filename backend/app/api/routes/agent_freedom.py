from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.deps import require_admin_user
from app.services.agent_freedom_service import (
    get_agent_portfolio_account,
    get_agent_portfolio_positions,
    get_agent_freedom_latest_report,
    list_agent_freedom_runs,
    list_agent_freedom_skill_calls,
    run_agent_freedom_daily,
    upsert_agent_portfolio_account,
    upsert_agent_portfolio_positions,
)

router = APIRouter()


class PortfolioAccountUpsertRequest(BaseModel):
    account_name: str = Field(default="Main Account", min_length=1, max_length=120)
    total_equity: float = Field(ge=0)
    cash: float = Field(default=0.0, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PortfolioPositionItem(BaseModel):
    ts_code: str = Field(min_length=1, max_length=20)
    stock_name: str = ""
    industry: str = ""
    position_type: str = ""
    quantity: float | None = Field(default=None, ge=0)
    shares: float | None = Field(default=None, ge=0)
    cost_price: float | None = Field(default=None, ge=0)
    current_price: float | None = Field(default=None, ge=0)
    market_value: float | None = Field(default=None, ge=0)
    entry_date: str | None = None
    holding_days: int | None = Field(default=None, ge=0)
    strategy_version_id: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class PortfolioPositionUpsertRequest(BaseModel):
    positions: list[PortfolioPositionItem] = Field(default_factory=list)
    snapshot_trade_date: str | None = None
    replace_all: bool = False


@router.post("/agent-freedom/run")
def run_agent_freedom(
    trade_date: str | None = Query(default=None),
    strategy_version_id: str | None = Query(default=None),
    account_id: str = Query(default="main"),
    current_user: dict[str, object] = Depends(require_admin_user),
) -> dict[str, Any]:
    del current_user
    try:
        return run_agent_freedom_daily(
            trade_date=trade_date,
            strategy_version_id=strategy_version_id,
            account_id=account_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/agent-freedom/report/latest")
def get_latest_report(
    trade_date: str | None = Query(default=None),
) -> dict[str, Any]:
    try:
        row = get_agent_freedom_latest_report(trade_date=trade_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not row:
        return {"item": None}
    return {"item": row}


@router.get("/agent-freedom/runs")
def list_runs(
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
) -> dict[str, Any]:
    try:
        items, total = list_agent_freedom_runs(
            start_date=start_date,
            end_date=end_date,
            status=status,
            page=page,
            page_size=page_size,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.put("/agent-freedom/portfolio/accounts/{account_id}")
def upsert_portfolio_account(
    account_id: str,
    payload: PortfolioAccountUpsertRequest,
    current_user: dict[str, object] = Depends(require_admin_user),
) -> dict[str, Any]:
    del current_user
    try:
        item = upsert_agent_portfolio_account(
            account_id=account_id,
            account_name=payload.account_name,
            total_equity=payload.total_equity,
            cash=payload.cash,
            metadata=payload.metadata,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"item": item}


@router.get("/agent-freedom/portfolio/accounts/{account_id}")
def get_portfolio_account(
    account_id: str,
    current_user: dict[str, object] = Depends(require_admin_user),
) -> dict[str, Any]:
    del current_user
    item = get_agent_portfolio_account(account_id=account_id)
    if not item:
        return {"item": None}
    return {"item": item}


@router.put("/agent-freedom/portfolio/positions/{account_id}")
def upsert_portfolio_positions(
    account_id: str,
    payload: PortfolioPositionUpsertRequest,
    current_user: dict[str, object] = Depends(require_admin_user),
) -> dict[str, Any]:
    del current_user
    try:
        result = upsert_agent_portfolio_positions(
            account_id=account_id,
            positions=[item.model_dump(exclude_none=True) for item in payload.positions],
            snapshot_trade_date=payload.snapshot_trade_date,
            replace_all=payload.replace_all,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result


@router.get("/agent-freedom/portfolio/positions/{account_id}")
def list_portfolio_positions(
    account_id: str,
    current_user: dict[str, object] = Depends(require_admin_user),
) -> dict[str, Any]:
    del current_user
    return get_agent_portfolio_positions(account_id=account_id)


@router.get("/agent-freedom/skill-calls")
def list_skill_calls(
    trade_date: str | None = Query(default=None),
    skill: str | None = Query(default=None),
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
) -> dict[str, Any]:
    try:
        items, total = list_agent_freedom_skill_calls(
            trade_date=trade_date,
            skill_name=skill,
            status=status,
            page=page,
            page_size=page_size,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }
