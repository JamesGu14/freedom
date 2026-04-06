from __future__ import annotations

from collections import Counter
from typing import Any

from app.audit.models import AuditRunResult
from app.data.mongo_data_integrity_audit import upsert_data_integrity_audit_run
from scripts.audit.run_data_integrity_audit import run_audit


def build_airflow_audit_run_document(
    *,
    result: AuditRunResult,
    dag_id: str,
    task_id: str,
    scheduled_for: str,
) -> dict[str, Any]:
    statuses = Counter(item.status for item in result.datasets)
    datasets = []
    for item in result.datasets:
        datasets.append(
            {
                "dataset": item.dataset,
                "status": item.status,
                "missing_dates": len(item.date_gap.missing_trade_dates),
                "coverage_anomalies": len(item.coverage_anomalies),
                "rowcount_anomalies": len(item.rowcount_anomalies),
                "local_min_date": item.local_min_date,
                "local_max_date": item.local_max_date,
            }
        )
    return {
        "run_id": result.run_id,
        "dag_id": dag_id,
        "task_id": task_id,
        "schedule": "0 6 * * 6",
        "scheduled_for": scheduled_for,
        "output_dir": result.output_dir,
        "status_summary": {
            "green": int(statuses.get("green", 0)),
            "yellow": int(statuses.get("yellow", 0)),
            "red": int(statuses.get("red", 0)),
        },
        "datasets": datasets,
        "summary": {
            "output_dir": result.output_dir,
            "excluded_datasets": list(result.excluded_datasets),
            "dataset_count": len(result.datasets),
        },
    }


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
