from __future__ import annotations

import datetime as dt

import pytest

from scripts.audit.run_data_integrity_audit_runner import (
    RunnerArgs,
    execute_run,
    parse_args,
)
from app.audit.models import AuditRunResult, DatasetAuditResult, DateGapResult


@pytest.fixture(autouse=True)
def disable_external_alerts(monkeypatch):
    monkeypatch.setattr("scripts.audit.run_data_integrity_audit_runner._notify_audit_result", lambda *_: None)


def _make_audit_result(run_id: str) -> AuditRunResult:
    return AuditRunResult(
        run_id=run_id,
        output_dir="/tmp/data_audit/test",
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
            )
        ],
    )


# ---------- parse_args ----------


def test_parse_args_minimum_required() -> None:
    args = parse_args(
        [
            "--run-id",
            "weekly_20260726",
            "--trigger-source",
            "airflow_weekly",
        ]
    )

    assert args.run_id == "weekly_20260726"
    assert args.trigger_source == "airflow_weekly"
    assert args.scheduled_for is None
    assert args.datasets == []
    assert args.start_date is None
    assert args.end_date is None


def test_parse_args_full_options() -> None:
    args = parse_args(
        [
            "--run-id",
            "manual_001",
            "--trigger-source",
            "manual",
            "--scheduled-for",
            "2026-07-26T06:00:00+08:00",
            "--datasets",
            "daily,daily_basic",
            "--start-date",
            "20240101",
            "--end-date",
            "20241231",
        ]
    )

    assert args.run_id == "manual_001"
    assert args.trigger_source == "manual"
    assert args.scheduled_for == "2026-07-26T06:00:00+08:00"
    assert args.datasets == ["daily", "daily_basic"]
    assert args.start_date == "20240101"
    assert args.end_date == "20241231"


def test_parse_args_strips_whitespace_in_datasets() -> None:
    args = parse_args(
        [
            "--run-id",
            "x",
            "--trigger-source",
            "t",
            "--datasets",
            " daily , daily_basic , indicators ",
        ]
    )

    assert args.datasets == ["daily", "daily_basic", "indicators"]


def test_parse_args_rejects_missing_run_id() -> None:
    with pytest.raises(SystemExit):
        parse_args(["--trigger-source", "t"])


@pytest.mark.parametrize("days", ["0", "-1"])
def test_parse_args_rejects_nonpositive_trade_day_window(days) -> None:
    with pytest.raises(SystemExit):
        parse_args(["--run-id", "x", "--trigger-source", "t", "--last-trade-days", days])


def test_execute_run_records_calendar_resolution_failure(monkeypatch) -> None:
    writes = []

    def fail_calendar(_):
        raise ValueError("calendar empty")

    monkeypatch.setattr("scripts.audit.run_data_integrity_audit_runner._resolve_recent_trade_days", fail_calendar)
    args = RunnerArgs(run_id="calendar_failure", trigger_source="manual", last_trade_days=20)

    assert execute_run(args, upsert_run=lambda record: writes.append(record)) == 1
    assert writes[-1]["status"] == "failed"
    assert "calendar empty" in writes[-1]["error_message"]


def test_execute_run_records_success_persistence_failure() -> None:
    writes = []

    def upsert(record):
        if record["status"] == "succeeded":
            raise RuntimeError("success write failed")
        writes.append(record)

    args = RunnerArgs(run_id="persist_failure", trigger_source="manual")
    assert execute_run(args, audit_runner=lambda **_: _make_audit_result(args.run_id), upsert_run=upsert) == 1
    assert writes[-1]["status"] == "failed"
    assert "success write failed" in writes[-1]["error_message"]


def test_recent_trade_days_query_supports_calendar_storage_types(monkeypatch) -> None:
    from scripts.audit.run_data_integrity_audit_runner import _resolve_recent_trade_days

    class Calendar:
        def find(self, query, projection):
            assert query["exchange"] == "SSE"
            assert set(query["is_open"]["$in"]) == {"1", 1}
            return self

        def sort(self, field, direction):
            assert (field, direction) == ("cal_date", -1)
            return self

        def limit(self, n):
            assert n == 2
            return [{"cal_date": "20261030"}, {"cal_date": "20261029"}]

    monkeypatch.setattr("app.data.mongo.get_collection", lambda _: Calendar())
    assert _resolve_recent_trade_days(2) == ("20261029", "20261030")


# ---------- execute_run: success path ----------


def test_execute_run_marks_running_then_succeeded_on_success() -> None:
    writes: list[dict[str, object]] = []

    def fake_upsert(record: dict[str, object]) -> None:
        writes.append(dict(record))

    def fake_runner(**kwargs):
        return _make_audit_result(str(kwargs["run_id"]))

    args = RunnerArgs(
        run_id="weekly_001",
        trigger_source="airflow_weekly",
        scheduled_for="2026-07-26T06:00:00+08:00",
        datasets=[],
        start_date=None,
        end_date=None,
    )

    exit_code = execute_run(args, audit_runner=fake_runner, upsert_run=fake_upsert)

    assert exit_code == 0
    assert len(writes) == 2

    running_write = writes[0]
    assert running_write["run_id"] == "weekly_001"
    assert running_write["status"] == "running"
    assert running_write["trigger_source"] == "airflow_weekly"
    assert "started_at" in running_write
    assert running_write["error_message"] == ""

    success_write = writes[1]
    assert success_write["run_id"] == "weekly_001"
    assert success_write["status"] == "succeeded"
    assert success_write["output_dir"] == "/tmp/data_audit/test"
    assert success_write["status_summary"] == {"green": 1, "yellow": 0, "red": 0}
    assert success_write["datasets"][0]["dataset"] == "daily"
    assert success_write["error_message"] == ""
    assert "finished_at" in success_write


def test_execute_run_passes_dataset_filter_to_runner() -> None:
    captured: dict[str, object] = {}

    def fake_upsert(record: dict[str, object]) -> None:
        return None

    def fake_runner(**kwargs):
        captured.update(kwargs)
        return _make_audit_result(str(kwargs["run_id"]))

    args = RunnerArgs(
        run_id="filtered",
        trigger_source="manual",
        scheduled_for=None,
        datasets=["daily", "daily_basic"],
        start_date="20240101",
        end_date="20241231",
    )

    execute_run(args, audit_runner=fake_runner, upsert_run=fake_upsert)

    assert captured["run_id"] == "filtered"
    assert captured["selected_names"] == ["daily", "daily_basic"]
    assert captured["start_date"] == "20240101"
    assert captured["end_date"] == "20241231"


# ---------- execute_run: failure path ----------


def test_execute_run_marks_failed_on_runner_exception() -> None:
    writes: list[dict[str, object]] = []

    def fake_upsert(record: dict[str, object]) -> None:
        writes.append(dict(record))

    def fake_runner(**kwargs):
        raise RuntimeError("audit boom")

    args = RunnerArgs(
        run_id="failed_run",
        trigger_source="manual",
        scheduled_for=None,
        datasets=[],
        start_date=None,
        end_date=None,
    )

    exit_code = execute_run(args, audit_runner=fake_runner, upsert_run=fake_upsert)

    assert exit_code == 1
    assert len(writes) == 2

    failed_write = writes[1]
    assert failed_write["run_id"] == "failed_run"
    assert failed_write["status"] == "failed"
    assert "audit boom" in str(failed_write["error_message"])
    assert "RuntimeError" in str(failed_write["error_message"])
    assert "finished_at" in failed_write


def test_execute_run_marks_failed_even_if_upsert_raises_after_failure() -> None:
    """Best-effort: if the failed-state write itself raises, we surface the original error."""
    call_count = {"n": 0}

    def fake_upsert(record: dict[str, object]) -> None:
        call_count["n"] += 1
        if call_count["n"] == 2:  # the failed-state write
            raise RuntimeError("mongo unavailable")

    def fake_runner(**kwargs):
        raise ValueError("audit failed first")

    args = RunnerArgs(
        run_id="double_fail",
        trigger_source="manual",
        scheduled_for=None,
        datasets=[],
        start_date=None,
        end_date=None,
    )

    # Should propagate the audit failure (exit 1) — not crash the process
    exit_code = execute_run(args, audit_runner=fake_runner, upsert_run=fake_upsert)

    assert exit_code == 1
    assert call_count["n"] == 2  # attempted the failed-state write
