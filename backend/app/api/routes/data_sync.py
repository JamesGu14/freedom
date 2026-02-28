from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.deps import require_admin_user
from app.services.data_sync_service import (
    create_sync_job,
    get_calendar_status,
    get_missing_dates,
    get_sync_job,
    get_sync_job_logs,
    stop_sync_job,
)

router = APIRouter()


def _default_start() -> str:
    today = dt.datetime.now().date()
    start = today - dt.timedelta(days=180)
    return start.strftime("%Y%m%d")


def _default_end() -> str:
    return dt.datetime.now().strftime("%Y%m%d")


class DataSyncJobCreateRequest(BaseModel):
    start_date: str = Field(min_length=8)
    end_date: str = Field(min_length=8)


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


@router.post("/data-sync/jobs")
def create_data_sync_job(
    payload: DataSyncJobCreateRequest,
    current_user: dict[str, object] = Depends(require_admin_user),
) -> dict[str, Any]:
    username = str(current_user.get("username") or "")
    try:
        return create_sync_job(
            start_date=payload.start_date,
            end_date=payload.end_date,
            created_by=username,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"unexpected error: {exc}") from exc


@router.get("/data-sync/jobs/{job_id}")
def get_data_sync_job(
    job_id: str,
    current_user: dict[str, object] = Depends(require_admin_user),
) -> dict[str, Any]:
    del current_user
    row = get_sync_job(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="job not found")
    return row


@router.get("/data-sync/jobs/{job_id}/logs")
def get_data_sync_job_log(
    job_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=200000, ge=1, le=1000000),
    current_user: dict[str, object] = Depends(require_admin_user),
) -> dict[str, Any]:
    del current_user
    try:
        return get_sync_job_logs(job_id, offset=offset, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/data-sync/jobs/{job_id}/stop")
def stop_data_sync_job(
    job_id: str,
    current_user: dict[str, object] = Depends(require_admin_user),
) -> dict[str, Any]:
    del current_user
    try:
        return stop_sync_job(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

