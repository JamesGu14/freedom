from __future__ import annotations

from fastapi import APIRouter, Query

from app.data.mongo_shenwan_daily import (
    build_avg_rankings,
    get_daily_rankings,
    list_latest_trade_dates,
    list_trade_dates,
)

router = APIRouter()


@router.get("/sector-ranking/dates")
def get_sector_ranking_dates(
    limit: int = Query(default=30, ge=1, le=200),
) -> dict[str, object]:
    items = list_trade_dates(limit=limit)
    return {"items": items, "total": len(items)}


@router.get("/sector-ranking/daily")
def get_sector_ranking_daily(
    trade_date: str | None = Query(default=None),
    level: int = Query(default=1, ge=1, le=3),
    top_n: int = Query(default=5, ge=1, le=50),
    bottom_n: int = Query(default=5, ge=1, le=50),
) -> dict[str, object]:
    if not trade_date:
        dates = list_latest_trade_dates(limit=1, level=level)
        trade_date = dates[0] if dates else None

    if not trade_date:
        return {"trade_date": None, "level": level, "total": 0, "top": [], "bottom": []}

    top, bottom, total = get_daily_rankings(
        trade_date=trade_date, level=level, top_n=top_n, bottom_n=bottom_n
    )
    return {
        "trade_date": trade_date,
        "level": level,
        "total": total,
        "top": top,
        "bottom": bottom,
    }


@router.get("/sector-ranking/history")
def get_sector_ranking_history(
    days: int = Query(default=5, ge=1, le=30),
    level: int = Query(default=1, ge=1, le=3),
    top_n: int = Query(default=5, ge=1, le=50),
    bottom_n: int = Query(default=5, ge=1, le=50),
) -> dict[str, object]:
    dates = list_latest_trade_dates(limit=days, level=level)
    data = []
    for trade_date in dates:
        top, bottom, _total = get_daily_rankings(
            trade_date=trade_date, level=level, top_n=top_n, bottom_n=bottom_n
        )
        data.append({"trade_date": trade_date, "top": top, "bottom": bottom})
    return {"level": level, "days": len(dates), "data": data}


@router.get("/sector-ranking/avg")
def get_sector_ranking_avg(
    calc_date: str | None = Query(default=None),
    level: int = Query(default=1, ge=1, le=3),
    top_n: int = Query(default=10, ge=1, le=50),
    bottom_n: int = Query(default=10, ge=1, le=50),
) -> dict[str, object]:
    dates = list_latest_trade_dates(limit=5, before_or_on=calc_date, level=level)
    result = build_avg_rankings(
        trade_dates=dates, level=level, top_n=top_n, bottom_n=bottom_n
    )
    return {
        "calc_date": dates[0] if dates else None,
        "level": level,
        "trade_dates": result.get("trade_dates", []),
        "strongest": result.get("strongest", []),
        "weakest": result.get("weakest", []),
    }
