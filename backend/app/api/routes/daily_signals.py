from __future__ import annotations

from fastapi import APIRouter, Query

from app.data.mongo import get_collection

router = APIRouter()


@router.get("/daily-signals/dates")
def list_daily_signal_dates() -> dict[str, list[str]]:
    collection = get_collection("daily_signal")
    dates = collection.distinct("trading_date")
    dates = sorted((d for d in dates if d), reverse=True)
    return {"items": dates}


@router.get("/daily-signals")
def list_daily_signals(
    trading_date: str | None = Query(default=None),
    stock_code: str | None = Query(default=None),
) -> dict[str, list[dict[str, object]]]:
    if not trading_date and not stock_code:
        return {"items": []}

    query: dict[str, object] = {}
    if trading_date:
        query["trading_date"] = trading_date
    if stock_code:
        query["stock_code"] = stock_code

    collection = get_collection("daily_signal")
    cursor = collection.find(query).sort([("trading_date", -1), ("stock_code", 1)])
    items: list[dict[str, object]] = []
    for doc in cursor:
        doc.pop("_id", None)
        items.append(doc)
    return {"items": items}
