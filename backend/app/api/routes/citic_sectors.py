from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.data.mongo_citic import (
    get_citic_by_index_code,
    list_citic_industry,
    list_citic_members,
)
from app.services.stocks_service import get_last_n_days_pct_chg

router = APIRouter()


@router.get("/citic-sectors")
def get_citic_sectors(
    level: int | None = Query(default=None, ge=1, le=3),
) -> dict[str, object]:
    items = list_citic_industry(level=level)
    return {"items": items, "total": len(items)}


@router.get("/citic-sectors/{index_code}")
def get_citic_sector_detail(
    index_code: str,
    is_new: str | None = Query(default="Y"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=200, ge=1, le=2000),
) -> dict[str, object]:
    industry = get_citic_by_index_code(index_code)
    if not industry:
        raise HTTPException(status_code=404, detail="sector not found")

    is_new_value = is_new.upper() if is_new else None
    if is_new_value == "ALL":
        is_new_value = None

    raw_members, total = list_citic_members(
        index_code=index_code,
        is_new=is_new_value,
        page=page,
        page_size=page_size,
    )

    ts_codes = [item.get("cons_code") for item in raw_members if item.get("cons_code")]
    pct_map = get_last_n_days_pct_chg(ts_codes, n=5) if ts_codes else {}

    members: list[dict[str, object]] = []
    for item in raw_members:
        ts_code = item.get("cons_code")
        entry = pct_map.get(ts_code, {}) if ts_code else {}
        members.append(
            {
                "ts_code": ts_code,
                "name": item.get("cons_name"),
                "index_code": item.get("index_code"),
                "industry_name": item.get("industry_name"),
                "level": item.get("level"),
                "in_date": item.get("in_date"),
                "out_date": item.get("out_date"),
                "is_new": item.get("is_new"),
                "pct_chg_5d": entry.get("pct_chg_nd"),
                "pct_chg_1": entry.get("pct_chg_1"),
                "pct_chg_2": entry.get("pct_chg_2"),
                "pct_chg_3": entry.get("pct_chg_3"),
                "pct_chg_4": entry.get("pct_chg_4"),
                "pct_chg_5": entry.get("pct_chg_5"),
                "pct_chg_1_date": entry.get("pct_chg_1_date"),
                "pct_chg_2_date": entry.get("pct_chg_2_date"),
                "pct_chg_3_date": entry.get("pct_chg_3_date"),
                "pct_chg_4_date": entry.get("pct_chg_4_date"),
                "pct_chg_5_date": entry.get("pct_chg_5_date"),
            }
        )

    return {
        "industry": industry,
        "members": members,
        "total": total,
        "page": page,
        "page_size": page_size,
    }

