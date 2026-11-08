from __future__ import annotations

from app.audit.models import (
    AuditRunResult,
    CoverageAnomaly,
    DatasetAuditResult,
    DateGapResult,
    RowCountAnomaly,
)
from app.audit.summary_builder import (
    build_audit_run_document,
    build_dataset_summary,
    build_status_summary,
)


def _make_dataset(
    *,
    name: str = "daily",
    status: str = "green",
    missing_dates: int = 0,
    coverage_anomalies: int = 0,
    rowcount_anomalies: int = 0,
) -> DatasetAuditResult:
    return DatasetAuditResult(
        dataset=name,
        audit_mode="date_only",
        local_min_date="20200101",
        local_max_date="20260314",
        status=status,
        date_gap=DateGapResult(
            local_min_date="20200101",
            local_max_date="20260314",
            expected_trade_date_count=100,
            actual_trade_date_count=100 - missing_dates,
            missing_trade_dates=[f"20200{i + 1}01" for i in range(missing_dates)],
            severity=status,
        ),
        coverage_anomalies=[
            CoverageAnomaly(
                dataset=name,
                trade_date=f"2020010{i + 1}",
                baseline_count=100,
                dataset_count=90,
                missing_count=10,
                coverage_ratio=0.9,
                severity="yellow",
            )
            for i in range(coverage_anomalies)
        ],
        rowcount_anomalies=[
            RowCountAnomaly(
                dataset=name,
                trade_date=f"2020010{i + 1}",
                row_count=50,
                median_lookback=100.0,
                baseline_count=100.0,
                baseline_source="median_20d",
                deviation_ratio=0.5,
                severity="red",
            )
            for i in range(rowcount_anomalies)
        ],
    )


def _make_result(*, datasets: list[DatasetAuditResult], run_id: str = "r1") -> AuditRunResult:
    return AuditRunResult(
        run_id=run_id,
        output_dir="/tmp/data_audit/r1",
        datasets=datasets,
        excluded_datasets=["cyq_chips"],
    )


def test_build_status_summary_counts_severities() -> None:
    result = _make_result(
        datasets=[
            _make_dataset(name="daily", status="green"),
            _make_dataset(name="daily_basic", status="yellow"),
            _make_dataset(name="daily_limit", status="red"),
            _make_dataset(name="indicators", status="green"),
        ]
    )

    summary = build_status_summary(result)

    assert summary == {"green": 2, "yellow": 1, "red": 1}


def test_build_status_summary_returns_zero_for_unknown_severities() -> None:
    result = _make_result(datasets=[_make_dataset(name="daily", status="green")])

    summary = build_status_summary(result)

    assert summary == {"green": 1, "yellow": 0, "red": 0}


def test_build_dataset_summary_includes_count_fields() -> None:
    result = _make_result(
        datasets=[
            _make_dataset(
                name="daily",
                status="yellow",
                missing_dates=3,
                coverage_anomalies=2,
                rowcount_anomalies=1,
            ),
        ]
    )

    rows = build_dataset_summary(result)

    assert len(rows) == 1
    row = rows[0]
    assert row["dataset"] == "daily"
    assert row["status"] == "yellow"
    assert row["missing_dates"] == 3
    assert row["coverage_anomalies"] == 2
    assert row["rowcount_anomalies"] == 1
    assert row["local_min_date"] == "20200101"
    assert row["local_max_date"] == "20260314"


def test_build_audit_run_document_combines_all_sections() -> None:
    result = _make_result(
        datasets=[
            _make_dataset(name="daily", status="green"),
            _make_dataset(name="daily_basic", status="red"),
        ]
    )

    document = build_audit_run_document(
        result=result,
        dag_id="freedom_data_integrity_weekly",
        task_id="run_weekly_audit",
        scheduled_for="2026-07-26T06:00:00+08:00",
    )

    assert document["run_id"] == "r1"
    assert document["dag_id"] == "freedom_data_integrity_weekly"
    assert document["task_id"] == "run_weekly_audit"
    assert document["scheduled_for"] == "2026-07-26T06:00:00+08:00"
    assert document["output_dir"] == "/tmp/data_audit/r1"
    assert document["status_summary"] == {"green": 1, "yellow": 0, "red": 1}
    assert document["summary"]["dataset_count"] == 2
    assert document["summary"]["excluded_datasets"] == ["cyq_chips"]
    assert document["summary"]["output_dir"] == "/tmp/data_audit/r1"
    assert [d["dataset"] for d in document["datasets"]] == ["daily", "daily_basic"]


def test_build_audit_run_document_omits_schedule_when_not_provided() -> None:
    result = _make_result(datasets=[_make_dataset()])

    document = build_audit_run_document(
        result=result,
        dag_id="d",
        task_id="t",
        scheduled_for="2026-07-26T06:00:00+08:00",
    )

    assert "schedule" not in document or document.get("schedule") is None
