import logging

from fastapi import APIRouter, HTTPException, Query

from app.services.stocks_service import get_industries, get_stock_basic, sync_stock_basic

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
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/stocks/industries")
def list_industries() -> dict[str, list[str]]:
    items = get_industries()
    return {"items": items}


@router.post("/stocks/sync")
def sync_stocks() -> dict[str, int]:
    try:
        result = sync_stock_basic()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to sync stock_basic")
        raise HTTPException(status_code=500, detail="同步失败，请检查服务日志") from exc
    return result


@router.get("/stocks/{ts_code}/candles")
def get_candles(ts_code: str) -> dict[str, str]:
    return {"ts_code": ts_code}


@router.get("/stocks/{ts_code}/features")
def get_features(ts_code: str) -> dict[str, str]:
    return {"ts_code": ts_code}
