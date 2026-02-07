from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.data.mongo_shenwan import (
    get_shenwan_by_index_code,
    get_shenwan_by_industry_code,
    list_shenwan_industry,
    list_shenwan_versions,
)
from app.data.mongo_shenwan_member import list_shenwan_members
from app.services.stocks_service import get_last_n_days_pct_chg

router = APIRouter()


@router.get("/shenwan-industries/versions")
def get_shenwan_versions() -> dict[str, list[str]]:
    versions = list_shenwan_versions()
    return {"items": versions}


@router.get("/shenwan-industries")
def get_shenwan_industries(
    version: str | None = Query(default="2021"),
    level: int | None = Query(default=None, ge=1, le=3),
    level1_code: str | None = Query(default=None),
    parent_code: str | None = Query(default=None),
    is_published: bool | None = Query(default=None),
) -> dict[str, list[dict[str, object]]]:
    items = list_shenwan_industry(
        version=version,
        level=level,
        level1_code=level1_code,
        parent_code=parent_code,
        is_published=is_published,
    )
    return {"items": items}


@router.get("/shenwan-members")
def get_shenwan_members(
    ts_code: str | None = Query(default=None),
    l1_code: str | None = Query(default=None),
    l2_code: str | None = Query(default=None),
    l3_code: str | None = Query(default=None),
    is_new: str | None = Query(default=None),
    version: str | None = Query(default="2021"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=200, ge=1, le=2000),
) -> dict[str, object]:
    is_new_value = is_new.upper() if is_new else None
    items, total = list_shenwan_members(
        ts_code=ts_code,
        l1_code=l1_code,
        l2_code=l2_code,
        l3_code=l3_code,
        is_new=is_new_value,
        version=version,
        page=page,
        page_size=page_size,
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/sectors/versions")
def get_sector_versions() -> dict[str, list[str]]:
    versions = list_shenwan_versions()
    return {"items": versions}


@router.get("/sectors")
def get_sectors(
    version: str | None = Query(default="2021"),
    level: int | None = Query(default=1, ge=1, le=3),
    level1_code: str | None = Query(default=None),
    parent_code: str | None = Query(default=None),
    is_published: bool | None = Query(default=True),
) -> dict[str, list[dict[str, object]]]:
    items = list_shenwan_industry(
        version=version,
        level=level,
        level1_code=level1_code,
        parent_code=parent_code,
        is_published=is_published,
    )
    return {"items": items}


@router.get("/sectors/members")
def get_sector_members(
    ts_code: str | None = Query(default=None),
    l1_code: str | None = Query(default=None),
    l2_code: str | None = Query(default=None),
    l3_code: str | None = Query(default=None),
    is_new: str | None = Query(default="Y"),
    version: str | None = Query(default="2021"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=200, ge=1, le=2000),
) -> dict[str, object]:
    is_new_value = is_new.upper() if is_new else None
    if is_new_value == "ALL":
        is_new_value = None
    items, total = list_shenwan_members(
        ts_code=ts_code,
        l1_code=l1_code,
        l2_code=l2_code,
        l3_code=l3_code,
        is_new=is_new_value,
        version=version,
        page=page,
        page_size=page_size,
    )
    ts_codes = [item.get("ts_code") for item in items if item.get("ts_code")]
    pct_map = get_last_n_days_pct_chg(ts_codes, n=3) if ts_codes else {}
    for item in items:
        code = item.get("ts_code")
        if code:
            entry = pct_map.get(code, {})
            item["pct_chg_3d"] = entry.get("pct_chg_nd")
            item["pct_chg_1"] = entry.get("pct_chg_1")
            item["pct_chg_2"] = entry.get("pct_chg_2")
            item["pct_chg_3"] = entry.get("pct_chg_3")
            item["pct_chg_1_date"] = entry.get("pct_chg_1_date")
            item["pct_chg_2_date"] = entry.get("pct_chg_2_date")
            item["pct_chg_3_date"] = entry.get("pct_chg_3_date")
        else:
            item["pct_chg_3d"] = item["pct_chg_1"] = item["pct_chg_2"] = item["pct_chg_3"] = None
            item["pct_chg_1_date"] = item["pct_chg_2_date"] = item["pct_chg_3_date"] = None
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/sectors/{index_code}")
def get_sector_detail(
    index_code: str,
    version: str | None = Query(default="2021"),
    is_new: str | None = Query(default="Y"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=200, ge=1, le=2000),
) -> dict[str, object]:
    industry = get_shenwan_by_index_code(index_code, version=version)
    if not industry:
        raise HTTPException(status_code=404, detail="sector not found")

    level = industry.get("level")
    filter_kwargs: dict[str, object] = {}
    if level == 1:
        filter_kwargs["l1_code"] = industry.get("index_code")
    elif level == 2:
        filter_kwargs["l2_code"] = industry.get("index_code")
    else:
        filter_kwargs["l3_code"] = industry.get("index_code")

    is_new_value = is_new.upper() if is_new else None
    if is_new_value == "ALL":
        is_new_value = None

    members, total = list_shenwan_members(
        is_new=is_new_value,
        version=version,
        page=page,
        page_size=page_size,
        **filter_kwargs,
    )

    ts_codes = [item.get("ts_code") for item in members if item.get("ts_code")]
    pct_map = get_last_n_days_pct_chg(ts_codes, n=5) if ts_codes else {}
    for item in members:
        code = item.get("ts_code")
        if code:
            entry = pct_map.get(code, {})
            item["pct_chg_5d"] = entry.get("pct_chg_nd")
            item["pct_chg_1"] = entry.get("pct_chg_1")
            item["pct_chg_2"] = entry.get("pct_chg_2")
            item["pct_chg_3"] = entry.get("pct_chg_3")
            item["pct_chg_4"] = entry.get("pct_chg_4")
            item["pct_chg_5"] = entry.get("pct_chg_5")
            item["pct_chg_1_date"] = entry.get("pct_chg_1_date")
            item["pct_chg_2_date"] = entry.get("pct_chg_2_date")
            item["pct_chg_3_date"] = entry.get("pct_chg_3_date")
            item["pct_chg_4_date"] = entry.get("pct_chg_4_date")
            item["pct_chg_5_date"] = entry.get("pct_chg_5_date")
        else:
            item["pct_chg_5d"] = (
                item["pct_chg_1"]
            ) = item["pct_chg_2"] = item["pct_chg_3"] = item["pct_chg_4"] = item["pct_chg_5"] = None
            item["pct_chg_1_date"] = (
                item["pct_chg_2_date"]
            ) = item["pct_chg_3_date"] = item["pct_chg_4_date"] = item["pct_chg_5_date"] = None

    breadcrumbs: list[dict[str, object]] = []
    level1_code = industry.get("level1_code")
    level2_code = industry.get("level2_code")
    if level1_code:
        level1 = get_shenwan_by_industry_code(str(level1_code), version=version)
        if level1:
            breadcrumbs.append(
                {
                    "level": 1,
                    "name": level1.get("industry_name"),
                    "index_code": level1.get("index_code"),
                }
            )
    if level2_code:
        level2 = get_shenwan_by_industry_code(str(level2_code), version=version)
        if level2:
            breadcrumbs.append(
                {
                    "level": 2,
                    "name": level2.get("industry_name"),
                    "index_code": level2.get("index_code"),
                }
            )
    if industry.get("level") == 3:
        breadcrumbs.append(
            {
                "level": 3,
                "name": industry.get("industry_name"),
                "index_code": industry.get("index_code"),
            }
        )

    return {
        "industry": industry,
        "members": members,
        "total": total,
        "page": page,
        "page_size": page_size,
        "breadcrumbs": breadcrumbs,
    }
