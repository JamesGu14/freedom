"""Shared builders for data integrity audit summaries.

Extracted from `app.audit.airflow_runner` and
`app.services.data_integrity_audit_job_service` to eliminate duplication and
provide a single source of truth for both the in-process runner, the CLI
runner, and the HTTP-triggered job service.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from app.audit.models import AuditRunResult


def build_status_summary(result: AuditRunResult) -> dict[str, int]:
    """Aggregate per-dataset severity into green/yellow/red counts."""
    statuses = Counter(item.status for item in result.datasets)
    return {
        "green": int(statuses.get("green", 0)),
        "yellow": int(statuses.get("yellow", 0)),
        "red": int(statuses.get("red", 0)),
    }


def build_dataset_summary(result: AuditRunResult) -> list[dict[str, Any]]:
    """Build a compact per-dataset summary row list suitable for MongoDB persistence."""
    rows: list[dict[str, Any]] = []
    for item in result.datasets:
        rows.append(
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
    return rows


def build_audit_run_document(
    *,
    result: AuditRunResult,
    dag_id: str,
    task_id: str,
    scheduled_for: str,
    schedule: str | None = None,
) -> dict[str, Any]:
    """Build the full audit run document for persistence.

    Args:
        result: The audit run result.
        dag_id: Airflow DAG id (or synthetic source identifier).
        task_id: Airflow task id (or synthetic source identifier).
        scheduled_for: ISO-formatted scheduled timestamp.
        schedule: Optional cron expression. Omitted from output when None.
    """
    document: dict[str, Any] = {
        "run_id": result.run_id,
        "dag_id": dag_id,
        "task_id": task_id,
        "scheduled_for": scheduled_for,
        "output_dir": result.output_dir,
        "status_summary": build_status_summary(result),
        "datasets": build_dataset_summary(result),
        "summary": {
            "output_dir": result.output_dir,
            "excluded_datasets": list(result.excluded_datasets),
            "dataset_count": len(result.datasets),
        },
    }
    if schedule is not None:
        document["schedule"] = schedule
    return document
