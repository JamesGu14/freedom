from __future__ import annotations

import json

from app.audit.models import AuditRunResult, CoverageAnomaly, DatasetAuditResult, DateGapResult, RowCountAnomaly
from app.audit.report_builder import write_audit_reports


def test_write_audit_reports_creates_expected_files(tmp_path) -> None:
    output_dir = tmp_path / "logs" / "data_audit" / "fixed-run"
    run_result = AuditRunResult(
        run_id="fixed-run",
        output_dir=str(output_dir),
        datasets=[
            DatasetAuditResult(
                dataset="daily_basic",
                audit_mode="date_and_coverage",
                local_min_date="20260303",
                local_max_date="20260305",
                status="red",
                date_gap=DateGapResult(
                    local_min_date="20260303",
                    local_max_date="20260305",
                    expected_trade_date_count=3,
                    actual_trade_date_count=2,
                    missing_trade_dates=["20260304"],
                    severity="yellow",
                ),
                coverage_anomalies=[
                    CoverageAnomaly(
                        dataset="daily_basic",
                        trade_date="20260305",
                        baseline_count=1000,
                        dataset_count=980,
                        missing_count=20,
                        coverage_ratio=0.98,
                        severity="red",
                    )
                ],
                rowcount_anomalies=[],
            )
        ],
        excluded_datasets=["stk_surv"],
    )

    written = write_audit_reports(output_dir, run_result)

    names = {path.name for path in written}
    assert "summary.md" in names
    assert "missing_dates.csv" in names
    assert "coverage_anomalies.csv" in names
    assert "rowcount_anomalies.csv" in names
    assert "summary.json" in names

    summary_json = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary_json["run_id"] == "fixed-run"
    assert summary_json["excluded_datasets"] == ["stk_surv"]
    assert summary_json["datasets"][0]["dataset"] == "daily_basic"
    assert "daily_basic" in (output_dir / "summary.md").read_text(encoding="utf-8")
