from __future__ import annotations

import datetime as dt

from bson import ObjectId
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.data.mongo_groups import (
    add_stock_to_group,
    create_group,
    get_group,
    list_group_items,
    list_groups,
    remove_stock_from_group,
)
from app.data.mongo_stock import get_stock_by_code
from app.services.stocks_service import get_latest_daily_changes

router = APIRouter()


class StockGroupCreatePayload(BaseModel):
    name: str = Field(min_length=1, max_length=64)


class StockGroupAddPayload(BaseModel):
    ts_code: str = Field(min_length=1, max_length=32)


def _parse_group_id(group_id: str) -> ObjectId:
    try:
        return ObjectId(group_id)
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=400, detail="Invalid group id") from exc


def _serialize_datetime(value: dt.datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt.UTC)
    return value.isoformat()


def _serialize_group(doc: dict[str, object]) -> dict[str, object]:
    return {
        "id": str(doc.get("_id")),
        "name": doc.get("name"),
        "created_at": _serialize_datetime(doc.get("created_at")),
        "count": int(doc.get("count", 0)),
    }


@router.get("/stock-groups")
def list_stock_groups() -> dict[str, list[dict[str, object]]]:
    items = [_serialize_group(doc) for doc in list_groups()]
    return {"items": items}


@router.post("/stock-groups")
def create_stock_group(payload: StockGroupCreatePayload) -> dict[str, object]:
    group = create_group(payload.name.strip())
    return _serialize_group(group)


@router.get("/stock-groups/{group_id}")
def get_stock_group(group_id: str) -> dict[str, object]:
    group = get_group(_parse_group_id(group_id))
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    return _serialize_group(group)


@router.get("/stock-groups/{group_id}/stocks")
def list_group_stocks(group_id: str) -> dict[str, list[dict[str, object]]]:
    group_obj_id = _parse_group_id(group_id)
    if not get_group(group_obj_id):
        raise HTTPException(status_code=404, detail="Group not found")
    items = list_group_items(group_obj_id)
    codes = [item.get("ts_code") for item in items if item.get("ts_code")]
    change_map = get_latest_daily_changes(codes)
    serialized = []
    for item in items:
        change = change_map.get(item.get("ts_code"))
        serialized.append(
            {
                "ts_code": item.get("ts_code"),
                "name": item.get("name"),
                "industry": item.get("industry"),
                "market": item.get("market"),
                "added_at": _serialize_datetime(item.get("added_at")),
                "latest_trade_date": change.get("trade_date") if change else None,
                "latest_change": change.get("change") if change else None,
                "latest_pct_chg": change.get("pct_chg") if change else None,
            }
        )
    return {"items": serialized}


@router.post("/stock-groups/{group_id}/stocks")
def add_group_stock(group_id: str, payload: StockGroupAddPayload) -> dict[str, bool]:
    group_obj_id = _parse_group_id(group_id)
    if not get_group(group_obj_id):
        raise HTTPException(status_code=404, detail="Group not found")
    ts_code = payload.ts_code.strip()
    stock = get_stock_by_code(ts_code)
    if not stock:
        raise HTTPException(status_code=400, detail="Stock not found")
    added = add_stock_to_group(group_obj_id, ts_code, stock_id=stock.get("_id"))
    return {"added": added}


@router.delete("/stock-groups/{group_id}/stocks/{ts_code}")
def remove_group_stock(group_id: str, ts_code: str) -> dict[str, bool]:
    group_obj_id = _parse_group_id(group_id)
    if not get_group(group_obj_id):
        raise HTTPException(status_code=404, detail="Group not found")
    removed = remove_stock_from_group(group_obj_id, ts_code.strip())
    return {"removed": removed}
