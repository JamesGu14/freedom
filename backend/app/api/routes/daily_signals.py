from __future__ import annotations

from fastapi import APIRouter, Query

from app.data.mongo import get_collection
from app.data.mongo_groups import list_group_names_by_stock_codes
from app.data.mongo_stock import get_stock_basic_map
from app.services.stocks_service import (
    get_daily_changes_for_date,
    get_latest_daily_changes,
    get_next_trade_date_for_codes,
)

router = APIRouter()


@router.get("/daily-signals/dates")
def list_daily_signal_dates() -> dict[str, list[str]]:
    collection = get_collection("daily_signal")
    dates = collection.distinct("trading_date")
    dates = sorted((d for d in dates if d), reverse=True)
    return {"items": dates}


@router.get("/daily-signals/strategies")
def list_daily_signal_strategies() -> dict[str, list[str]]:
    collection = get_collection("daily_signal")
    strategies = collection.distinct("strategy")
    strategies = sorted((s for s in strategies if s))
    return {"items": strategies}


@router.get("/daily-signals")
def list_daily_signals(
    trading_date: str | None = Query(default=None),
    stock_code: str | None = Query(default=None),
    strategy: str | None = Query(default=None),
    signal: str | None = Query(default=None),
) -> dict[str, list[dict[str, object]]]:
    if not trading_date and not stock_code and not strategy and not signal:
        return {"items": []}

    query: dict[str, object] = {}
    if trading_date:
        query["trading_date"] = trading_date
    if stock_code:
        query["stock_code"] = stock_code
    if strategy:
        query["strategy"] = strategy
    if signal:
        query["signal"] = signal.strip().upper()

    collection = get_collection("daily_signal")
    cursor = collection.find(query).sort([("trading_date", -1), ("stock_code", 1)])
    items: list[dict[str, object]] = []
    for doc in cursor:
        doc.pop("_id", None)
        items.append(doc)

    if not items:
        return {"items": []}

    codes = sorted({item.get("stock_code") for item in items if item.get("stock_code")})
    basics_map = get_stock_basic_map(codes)
    group_map = list_group_names_by_stock_codes(codes)
    next_trade_date = None
    if trading_date:
        next_trade_date = get_next_trade_date_for_codes(codes, trading_date)
    change_map = (
        get_daily_changes_for_date(codes, next_trade_date)
        if next_trade_date
        else get_latest_daily_changes(codes)
    )

    for item in items:
        code = item.get("stock_code")
        basic = basics_map.get(code, {})
        item["name"] = basic.get("name")
        item["industry"] = basic.get("industry")
        item["groups"] = group_map.get(code, [])
        change = change_map.get(code)
        if change:
            item["next_trade_date"] = change.get("trade_date")
            item["next_change"] = change.get("change")
            item["next_pct_chg"] = change.get("pct_chg")
        else:
            item["next_trade_date"] = next_trade_date

    return {"items": items}
