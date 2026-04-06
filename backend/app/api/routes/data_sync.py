from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import require_admin_user
from app.services.data_sync_service import get_calendar_status, get_missing_dates

router = APIRouter()


def _default_start() -> str:
    today = dt.datetime.now().date()
    start = today - dt.timedelta(days=180)
    return start.strftime("%Y%m%d")


def _default_end() -> str:
    return dt.datetime.now().strftime("%Y%m%d")


@router.get("/data-sync/calendar")
def get_data_sync_calendar(
    start_date: str = Query(default=""),
    end_date: str = Query(default=""),
    current_user: dict[str, object] = Depends(require_admin_user),
) -> dict[str, Any]:
    del current_user
    try:
        normalized_start = start_date or _default_start()
        normalized_end = end_date or _default_end()
        return get_calendar_status(start_date=normalized_start, end_date=normalized_end)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/data-sync/missing")
def get_data_sync_missing(
    start_date: str = Query(default=""),
    end_date: str = Query(default=""),
    current_user: dict[str, object] = Depends(require_admin_user),
) -> dict[str, Any]:
    del current_user
    try:
        normalized_start = start_date or _default_start()
        normalized_end = end_date or _default_end()
        return get_missing_dates(start_date=normalized_start, end_date=normalized_end)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
