from __future__ import annotations

from app.audit.airflow_runner import (
    build_airflow_audit_run_document,
    persist_airflow_audit_run,
    run_weekly_airflow_audit,
)
from app.audit.models import AuditRunResult, DatasetAuditResult, DateGapResult


def _build_result() -> AuditRunResult:
    return AuditRunResult(
        run_id="weekly_20260314_060000",
        output_dir="/tmp/data_audit/weekly_20260314_060000",
        excluded_datasets=["cyq_chips"],
        datasets=[
            DatasetAuditResult(
                dataset="daily",
                audit_mode="date_only",
                local_min_date="20200101",
                local_max_date="20260314",
                status="green",
                date_gap=DateGapResult(
                    local_min_date="20200101",
                    local_max_date="20260314",
                    expected_trade_date_count=100,
                    actual_trade_date_count=100,
                    missing_trade_dates=[],
                    severity="green",
                ),
            ),
            DatasetAuditResult(
                dataset="market_index_dailybasic",
                audit_mode="date_and_rowcount",
                local_min_date="20200101",
                local_max_date="20260314",
                status="yellow",
                date_gap=DateGapResult(
                    local_min_date="20200101",
                    local_max_date="20260314",
                    expected_trade_date_count=100,
                    actual_trade_date_count=100,
                    missing_trade_dates=[],
                    severity="green",
                ),
            ),
        ],
    )


def test_build_airflow_audit_run_document_summarizes_result() -> None:
    document = build_airflow_audit_run_document(
        result=_build_result(),
        dag_id="freedom_data_integrity_weekly",
        task_id="run_weekly_data_integrity_audit",
        scheduled_for="2026-03-14T06:00:00+08:00",
    )

    assert document["run_id"] == "weekly_20260314_060000"
    assert document["dag_id"] == "freedom_data_integrity_weekly"
    assert document["task_id"] == "run_weekly_data_integrity_audit"
    assert document["scheduled_for"] == "2026-03-14T06:00:00+08:00"
    assert document["status_summary"] == {"green": 1, "yellow": 1, "red": 0}
    assert document["datasets"][0]["dataset"] == "daily"
    assert document["datasets"][1]["status"] == "yellow"
    assert document["summary"]["excluded_datasets"] == ["cyq_chips"]


def test_persist_airflow_audit_run_delegates_to_mongo_helper(monkeypatch) -> None:
    seen: list[dict[str, object]] = []
    monkeypatch.setattr("app.audit.airflow_runner.upsert_data_integrity_audit_run", lambda payload: seen.append(payload))

    payload = {"run_id": "weekly_20260314_060000"}
    persist_airflow_audit_run(payload)

    assert seen == [payload]


def test_run_weekly_airflow_audit_runs_local_audit_and_persists(monkeypatch) -> None:
    seen: list[dict[str, object]] = []
    monkeypatch.setattr("app.audit.airflow_runner.persist_airflow_audit_run", lambda payload: seen.append(payload))
    monkeypatch.setattr("app.audit.airflow_runner.run_audit", lambda **kwargs: _build_result())

    payload = run_weekly_airflow_audit(
        dag_id="freedom_data_integrity_weekly",
        task_id="run_weekly_data_integrity_audit",
        scheduled_for="2026-03-14T06:00:00+08:00",
    )

    assert payload["run_id"] == "weekly_20260314_060000"
    assert payload["status_summary"] == {"green": 1, "yellow": 1, "red": 0}
    assert seen == [payload]
