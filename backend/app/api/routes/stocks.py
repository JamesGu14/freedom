import logging

from fastapi import APIRouter, HTTPException, Query

from app.api.stock_code import resolve_ts_code_input
from app.services.stocks_service import (
    get_adj_factor,
    get_daily,
    get_indicators,
    get_industries,
    get_stock_basic,
    get_stock_basic_by_ts_code,
    get_latest_daily_changes,
    sync_stock_basic,
)

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/stocks")
def list_stocks(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    name: str | None = Query(default=None),
    ts_code: str | None = Query(default=None),
    industry: str | None = Query(default=None),
) -> dict[str, object]:
    items, total = get_stock_basic(
        page=page,
        page_size=page_size,
        name=name,
        ts_code=ts_code,
        industry=industry,
    )
    codes = [item.get("ts_code") for item in items if item.get("ts_code")]
    change_map = get_latest_daily_changes(codes)
    for item in items:
        change = change_map.get(item.get("ts_code"))
        if not change:
            continue
        item["latest_trade_date"] = change.get("trade_date")
        item["latest_change"] = change.get("change")
        item["latest_pct_chg"] = change.get("pct_chg")
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/stocks/industries")
def list_industries() -> dict[str, list[str]]:
    items = get_industries()
    return {"items": items}


@router.post("/stocks/sync")
def sync_stocks(source: str | None = Query(default=None)) -> dict[str, int | str]:
    try:
        result = sync_stock_basic(source)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to sync stock_basic")
        raise HTTPException(status_code=500, detail="同步失败，请检查服务日志") from exc
    return result


@router.get("/stocks/{ts_code}/candles")
def get_candles(
    ts_code: str,
    limit: int | None = Query(default=None, ge=1, le=2000),
) -> dict[str, object]:
    normalized = resolve_ts_code_input(ts_code, strict=False)
    daily = get_daily(normalized, limit=limit)
    adj_factor = get_adj_factor(normalized, limit=limit)
    return {"ts_code": normalized, "daily": daily, "adj_factor": adj_factor}


@router.get("/stocks/{ts_code}/basic")
def get_basic(ts_code: str) -> dict[str, object]:
    normalized = resolve_ts_code_input(ts_code, strict=False)
    data = get_stock_basic_by_ts_code(normalized)
    if not data:
        raise HTTPException(status_code=404, detail="Stock not found")
    return data


@router.get("/stocks/{ts_code}/features")
def get_features(
    ts_code: str,
    limit: int | None = Query(default=None, ge=1, le=2000),
) -> dict[str, object]:
    normalized = resolve_ts_code_input(ts_code, strict=False)
    indicators = get_indicators(normalized, limit=limit)
    return {"ts_code": normalized, "indicators": indicators}
