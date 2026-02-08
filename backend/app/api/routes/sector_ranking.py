from __future__ import annotations

from fastapi import APIRouter, Query

from app.data.mongo_citic_daily import (
    build_citic_avg_rankings,
    get_citic_level_member_totals,
    get_citic_daily_rankings,
    list_citic_trade_dates,
    list_latest_citic_trade_dates,
)
from app.data.mongo_shenwan_daily import (
    build_avg_rankings,
    get_shenwan_level_member_totals,
    get_daily_rankings,
    list_latest_trade_dates,
    list_trade_dates,
)

router = APIRouter()


def _normalize_source(source: str | None) -> str:
    value = str(source or "sw").strip().lower()
    if value not in {"sw", "ci"}:
        return "sw"
    return value


@router.get("/sector-ranking/dates")
def get_sector_ranking_dates(
    limit: int = Query(default=30, ge=1, le=200),
    source: str = Query(default="sw"),
) -> dict[str, object]:
    source_value = _normalize_source(source)
    if source_value == "ci":
        items = list_citic_trade_dates(limit=limit)
    else:
        items = list_trade_dates(limit=limit)
    return {"source": source_value, "items": items, "total": len(items)}


@router.get("/sector-ranking/level-totals")
def get_sector_ranking_level_totals(
    source: str = Query(default="sw"),
) -> dict[str, object]:
    source_value = _normalize_source(source)
    if source_value == "ci":
        result = get_citic_level_member_totals()
    else:
        result = get_shenwan_level_member_totals()
    return {
        "source": source_value,
        "latest_trade_date": result.get("latest_trade_date"),
        "levels": result.get("levels", []),
    }


@router.get("/sector-ranking/daily")
def get_sector_ranking_daily(
    trade_date: str | None = Query(default=None),
    level: int = Query(default=1, ge=1, le=3),
    top_n: int = Query(default=5, ge=1, le=50),
    bottom_n: int = Query(default=5, ge=1, le=50),
    source: str = Query(default="sw"),
) -> dict[str, object]:
    source_value = _normalize_source(source)
    if not trade_date:
        if source_value == "ci":
            dates = list_latest_citic_trade_dates(limit=1, level=level)
        else:
            dates = list_latest_trade_dates(limit=1, level=level)
        trade_date = dates[0] if dates else None

    if not trade_date:
        return {
            "source": source_value,
            "trade_date": None,
            "level": level,
            "total": 0,
            "top": [],
            "bottom": [],
        }

    if source_value == "ci":
        top, bottom, total = get_citic_daily_rankings(
            trade_date=trade_date, level=level, top_n=top_n, bottom_n=bottom_n
        )
    else:
        top, bottom, total = get_daily_rankings(
            trade_date=trade_date, level=level, top_n=top_n, bottom_n=bottom_n
        )
    return {
        "source": source_value,
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
    source: str = Query(default="sw"),
) -> dict[str, object]:
    source_value = _normalize_source(source)
    if source_value == "ci":
        dates = list_latest_citic_trade_dates(limit=days, level=level)
    else:
        dates = list_latest_trade_dates(limit=days, level=level)
    data = []
    for trade_date in dates:
        if source_value == "ci":
            top, bottom, _total = get_citic_daily_rankings(
                trade_date=trade_date, level=level, top_n=top_n, bottom_n=bottom_n
            )
        else:
            top, bottom, _total = get_daily_rankings(
                trade_date=trade_date, level=level, top_n=top_n, bottom_n=bottom_n
            )
        data.append({"trade_date": trade_date, "top": top, "bottom": bottom})
    return {"source": source_value, "level": level, "days": len(dates), "data": data}


@router.get("/sector-ranking/avg")
def get_sector_ranking_avg(
    calc_date: str | None = Query(default=None),
    level: int = Query(default=1, ge=1, le=3),
    top_n: int = Query(default=10, ge=1, le=50),
    bottom_n: int = Query(default=10, ge=1, le=50),
    source: str = Query(default="sw"),
) -> dict[str, object]:
    source_value = _normalize_source(source)
    if source_value == "ci":
        dates = list_latest_citic_trade_dates(limit=5, before_or_on=calc_date, level=level)
        result = build_citic_avg_rankings(
            trade_dates=dates, level=level, top_n=top_n, bottom_n=bottom_n
        )
    else:
        dates = list_latest_trade_dates(limit=5, before_or_on=calc_date, level=level)
        result = build_avg_rankings(
            trade_dates=dates, level=level, top_n=top_n, bottom_n=bottom_n
        )
    return {
        "source": source_value,
        "calc_date": dates[0] if dates else None,
        "level": level,
        "trade_dates": result.get("trade_dates", []),
        "strongest": result.get("strongest", []),
        "weakest": result.get("weakest", []),
    }
