from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.deps import get_current_user, get_shared_business_username
from app.services.strategy_service import (
    create_strategy,
    create_version,
    enable_strategy,
    get_strategy,
    get_strategy_versions,
    list_available_engine_strategies,
    list_strategies,
    update_strategy,
)

router = APIRouter()


class StrategyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    strategy_key: str = Field(min_length=1, max_length=80)
    description: str = ""
    owner: str = ""


class StrategyUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    owner: str | None = None


class StrategyVersionCreateRequest(BaseModel):
    params_snapshot: dict[str, Any] = Field(default_factory=dict)
    code_ref: str = ""
    change_log: str = ""
    version: str | None = None


@router.get("/strategies/engine")
def list_engine_strategies() -> dict[str, Any]:
    items = list_available_engine_strategies()
    return {"items": items, "total": len(items)}


@router.get("/strategies")
def list_strategy_items(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    status: str | None = Query(default=None),
    keyword: str | None = Query(default=None),
) -> dict[str, Any]:
    items, total = list_strategies(
        page=page,
        page_size=page_size,
        status=status,
        keyword=keyword,
    )
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/strategies")
def create_strategy_item(
    payload: StrategyCreateRequest,
    current_user: dict[str, object] = Depends(get_current_user),
) -> dict[str, Any]:
    del current_user
    try:
        item = create_strategy(
            name=payload.name,
            strategy_key=payload.strategy_key,
            description=payload.description,
            owner=payload.owner,
            created_by=get_shared_business_username(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return item


@router.put("/strategies/{strategy_id}")
def update_strategy_item(
    strategy_id: str,
    payload: StrategyUpdateRequest,
) -> dict[str, Any]:
    try:
        item = update_strategy(
            strategy_id=strategy_id,
            name=payload.name,
            description=payload.description,
            owner=payload.owner,
        )
    except ValueError as exc:
        detail = str(exc)
        if "not found" in detail:
            raise HTTPException(status_code=404, detail=detail) from exc
        raise HTTPException(status_code=400, detail=detail) from exc
    return item


@router.post("/strategies/{strategy_id}/enable")
def enable_strategy_item(strategy_id: str) -> dict[str, Any]:
    if not enable_strategy(strategy_id, enabled=True):
        raise HTTPException(status_code=404, detail="strategy not found")
    item = get_strategy(strategy_id)
    return {"strategy_id": strategy_id, "status": "active", "item": item}


@router.post("/strategies/{strategy_id}/disable")
def disable_strategy_item(strategy_id: str) -> dict[str, Any]:
    if not enable_strategy(strategy_id, enabled=False):
        raise HTTPException(status_code=404, detail="strategy not found")
    item = get_strategy(strategy_id)
    return {"strategy_id": strategy_id, "status": "inactive", "item": item}


@router.get("/strategies/{strategy_id}/versions")
def list_versions(strategy_id: str) -> dict[str, Any]:
    strategy = get_strategy(strategy_id)
    if not strategy:
        raise HTTPException(status_code=404, detail="strategy not found")
    items = get_strategy_versions(strategy_id)
    return {"strategy_id": strategy_id, "items": items, "total": len(items)}


@router.post("/strategies/{strategy_id}/versions")
def create_strategy_version(
    strategy_id: str,
    payload: StrategyVersionCreateRequest,
    current_user: dict[str, object] = Depends(get_current_user),
) -> dict[str, Any]:
    del current_user
    try:
        item = create_version(
            strategy_id=strategy_id,
            params_snapshot=payload.params_snapshot,
            code_ref=payload.code_ref,
            change_log=payload.change_log,
            created_by=get_shared_business_username(),
            version=payload.version,
        )
    except ValueError as exc:
        detail = str(exc)
        if "not found" in detail:
            raise HTTPException(status_code=404, detail=detail) from exc
        raise HTTPException(status_code=400, detail=detail) from exc
    return item
