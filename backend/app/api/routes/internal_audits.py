from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import require_admin_user
from app.services.data_integrity_audit_job_service import (
    get_data_integrity_audit_run_status,
    start_data_integrity_audit_run,
)

router = APIRouter()


class DataIntegrityAuditRunCreateRequest(BaseModel):
    scheduled_for: str | None = None
    trigger_source: str = Field(default="manual", min_length=1)
    datasets: list[str] = Field(default_factory=list)
    start_date: str | None = None
    end_date: str | None = None


@router.post("/internal/audits/data-integrity/runs", status_code=status.HTTP_202_ACCEPTED)
def create_data_integrity_audit_run(
    payload: DataIntegrityAuditRunCreateRequest,
    current_user: dict[str, object] = Depends(require_admin_user),
) -> dict[str, Any]:
    requested_by = str(current_user.get("username") or "").strip() or "unknown"
    return start_data_integrity_audit_run(
        trigger_source=payload.trigger_source,
        requested_by=requested_by,
        scheduled_for=payload.scheduled_for,
        selected_datasets=payload.datasets,
        start_date=payload.start_date,
        end_date=payload.end_date,
    )


@router.get("/internal/audits/data-integrity/runs/{run_id}")
def get_data_integrity_audit_run(
    run_id: str,
    current_user: dict[str, object] = Depends(require_admin_user),
) -> dict[str, Any]:
    del current_user
    record = get_data_integrity_audit_run_status(run_id)
    if not record:
        raise HTTPException(status_code=404, detail="audit run not found")
    return record
