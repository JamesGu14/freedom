from __future__ import annotations

import datetime as dt
import threading
from collections import Counter
from typing import Any, Callable

from app.audit.models import AuditRunResult
from app.data.mongo_data_integrity_audit import get_data_integrity_audit_run, upsert_data_integrity_audit_run
from scripts.audit.run_data_integrity_audit import build_run_id, run_audit


AuditRunner = Callable[..., AuditRunResult]
UpsertRun = Callable[[dict[str, Any]], None]
GetRun = Callable[[str], dict[str, Any] | None]


class DataIntegrityAuditJobService:
    def __init__(
        self,
        *,
        audit_runner: AuditRunner = run_audit,
        upsert_run: UpsertRun = upsert_data_integrity_audit_run,
        get_run: GetRun = get_data_integrity_audit_run,
        thread_factory: Callable[..., Any] = threading.Thread,
        run_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._audit_runner = audit_runner
        self._upsert_run = upsert_run
        self._get_run = get_run
        self._thread_factory = thread_factory
        self._run_id_factory = run_id_factory or self._default_run_id

    def start_run(
        self,
        *,
        trigger_source: str,
        requested_by: str,
        scheduled_for: str | None = None,
        selected_datasets: list[str] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        run_id = self._run_id_factory()
        self._upsert_run(
            {
                "run_id": run_id,
                "status": "queued",
                "trigger_source": str(trigger_source or "manual"),
                "requested_by": str(requested_by or "").strip(),
                "scheduled_for": scheduled_for,
                "selected_datasets": list(selected_datasets or []),
                "start_date": start_date,
                "end_date": end_date,
                "error_message": "",
            }
        )
        thread = self._thread_factory(
            target=self._execute_run,
            kwargs={
                "run_id": run_id,
                "trigger_source": trigger_source,
                "scheduled_for": scheduled_for,
                "selected_datasets": list(selected_datasets or []),
                "start_date": start_date,
                "end_date": end_date,
            },
            daemon=True,
        )
        thread.start()
        return self.get_run(run_id) or {"run_id": run_id, "status": "queued"}

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        record = self._get_run(run_id)
        if not record:
            return None
        return _serialize_record(record)

    def _execute_run(
        self,
        *,
        run_id: str,
        trigger_source: str,
        scheduled_for: str | None,
        selected_datasets: list[str],
        start_date: str | None,
        end_date: str | None,
    ) -> None:
        started_at = _now_utc()
        self._upsert_run(
            {
                "run_id": run_id,
                "status": "running",
                "trigger_source": trigger_source,
                "scheduled_for": scheduled_for,
                "selected_datasets": selected_datasets,
                "start_date": start_date,
                "end_date": end_date,
                "started_at": started_at,
                "error_message": "",
            }
        )
        try:
            result = self._audit_runner(
                selected_names=selected_datasets or None,
                run_id=run_id,
                start_date=start_date,
                end_date=end_date,
            )
        except Exception as exc:
            self._upsert_run(
                {
                    "run_id": run_id,
                    "status": "failed",
                    "finished_at": _now_utc(),
                    "error_message": str(exc),
                }
            )
            return

        self._upsert_run(
            {
                "run_id": run_id,
                "status": "succeeded",
                "finished_at": _now_utc(),
                "output_dir": result.output_dir,
                "status_summary": _build_status_summary(result),
                "datasets": _build_dataset_summary(result),
                "summary": {
                    "dataset_count": len(result.datasets),
                    "excluded_datasets": list(result.excluded_datasets),
                    "output_dir": result.output_dir,
                },
                "error_message": "",
            }
        )

    def _default_run_id(self) -> str:
        return f"async_{build_run_id()}"


def _now_utc() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _build_status_summary(result: AuditRunResult) -> dict[str, int]:
    statuses = Counter(item.status for item in result.datasets)
    return {
        "green": int(statuses.get("green", 0)),
        "yellow": int(statuses.get("yellow", 0)),
        "red": int(statuses.get("red", 0)),
    }


def _build_dataset_summary(result: AuditRunResult) -> list[dict[str, Any]]:
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


def _serialize_record(record: dict[str, Any]) -> dict[str, Any]:
    serialized: dict[str, Any] = {}
    for key, value in record.items():
        if isinstance(value, dt.datetime):
            serialized[key] = value.isoformat()
        elif isinstance(value, list):
            serialized[key] = [_serialize_record(item) if isinstance(item, dict) else item for item in value]
        elif isinstance(value, dict):
            serialized[key] = _serialize_record(value)
        else:
            serialized[key] = value
    return serialized


_service = DataIntegrityAuditJobService()


def start_data_integrity_audit_run(
    *,
    trigger_source: str,
    requested_by: str,
    scheduled_for: str | None = None,
    selected_datasets: list[str] | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    return _service.start_run(
        trigger_source=trigger_source,
        requested_by=requested_by,
        scheduled_for=scheduled_for,
        selected_datasets=selected_datasets,
        start_date=start_date,
        end_date=end_date,
    )


def get_data_integrity_audit_run_status(run_id: str) -> dict[str, Any] | None:
    return _service.get_run(run_id)
