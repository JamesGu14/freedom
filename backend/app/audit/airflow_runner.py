from __future__ import annotations

from typing import Any

from app.audit.summary_builder import build_audit_run_document
from app.audit.models import AuditRunResult
from app.data.mongo_data_integrity_audit import upsert_data_integrity_audit_run
from scripts.audit.run_data_integrity_audit import run_audit


WEEKLY_SCHEDULE = "0 6 * * 6"


def build_airflow_audit_run_document(
    *,
    result: AuditRunResult,
    dag_id: str,
    task_id: str,
    scheduled_for: str,
) -> dict[str, Any]:
    return build_audit_run_document(
        result=result,
        dag_id=dag_id,
        task_id=task_id,
        scheduled_for=scheduled_for,
        schedule=WEEKLY_SCHEDULE,
    )


def persist_airflow_audit_run(payload: dict[str, Any]) -> None:
    upsert_data_integrity_audit_run(payload)


def run_weekly_airflow_audit(
    *,
    dag_id: str,
    task_id: str,
    scheduled_for: str,
) -> dict[str, Any]:
    run_id = _build_weekly_run_id(scheduled_for)
    result = run_audit(run_id=run_id)
    payload = build_airflow_audit_run_document(
        result=result,
        dag_id=dag_id,
        task_id=task_id,
        scheduled_for=scheduled_for,
    )
    persist_airflow_audit_run(payload)
    return payload


def _build_weekly_run_id(scheduled_for: str) -> str:
    compact = (
        str(scheduled_for)
        .replace("-", "")
        .replace(":", "")
        .replace("T", "_")
        .replace("+0800", "")
        .replace("+08:00", "")
    )
    return f"weekly_{compact}"
