from __future__ import annotations

from app.audit.models import AuditRunResult, DatasetAuditResult, DateGapResult
from app.services.data_integrity_audit_job_service import DataIntegrityAuditJobService


class _FakeThread:
    def __init__(self, *, target, kwargs=None, daemon=None):  # noqa: ANN001
        self.target = target
        self.kwargs = kwargs or {}
        self.daemon = daemon
        self.started = False

    def start(self) -> None:
        self.started = True

    def run_now(self) -> None:
        self.target(**self.kwargs)


def _build_result() -> AuditRunResult:
    return AuditRunResult(
        run_id="placeholder",
        output_dir="/tmp/data_audit/async_run",
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
        ],
    )


def test_start_run_creates_queued_run_and_completes_in_background() -> None:
    store: dict[str, dict[str, object]] = {}
    created_threads: list[_FakeThread] = []

    def upsert_run(record: dict[str, object]) -> None:
        current = dict(store.get(str(record["run_id"]), {}))
        current.update(record)
        store[str(record["run_id"])] = current

    def get_run(run_id: str) -> dict[str, object] | None:
        record = store.get(run_id)
        return dict(record) if record else None

    def runner(**kwargs):  # noqa: ANN003
        result = _build_result()
        result.run_id = str(kwargs["run_id"])
        return result

    def thread_factory(*, target, kwargs=None, daemon=None):  # noqa: ANN001
        thread = _FakeThread(target=target, kwargs=kwargs, daemon=daemon)
        created_threads.append(thread)
        return thread

    service = DataIntegrityAuditJobService(
        audit_runner=runner,
        upsert_run=upsert_run,
        get_run=get_run,
        thread_factory=thread_factory,
        run_id_factory=lambda: "generated_run_id",
    )

    queued = service.start_run(trigger_source="airflow", requested_by="james", scheduled_for="2026-03-21T06:00:00+08:00")

    assert queued["run_id"] == "generated_run_id"
    assert queued["status"] == "queued"
    assert queued["trigger_source"] == "airflow"
    assert created_threads[0].started is True

    created_threads[0].run_now()

    completed = service.get_run("generated_run_id")
    assert completed is not None
    assert completed["status"] == "succeeded"
    assert completed["output_dir"] == "/tmp/data_audit/async_run"
    assert completed["status_summary"] == {"green": 1, "yellow": 0, "red": 0}
    assert completed["datasets"][0]["dataset"] == "daily"


def test_run_failure_is_persisted_as_failed_status() -> None:
    store: dict[str, dict[str, object]] = {}
    created_threads: list[_FakeThread] = []

    def upsert_run(record: dict[str, object]) -> None:
        current = dict(store.get(str(record["run_id"]), {}))
        current.update(record)
        store[str(record["run_id"])] = current

    def get_run(run_id: str) -> dict[str, object] | None:
        record = store.get(run_id)
        return dict(record) if record else None

    def runner(**kwargs):  # noqa: ANN003, ARG001
        raise RuntimeError("boom")

    def thread_factory(*, target, kwargs=None, daemon=None):  # noqa: ANN001
        thread = _FakeThread(target=target, kwargs=kwargs, daemon=daemon)
        created_threads.append(thread)
        return thread

    service = DataIntegrityAuditJobService(
        audit_runner=runner,
        upsert_run=upsert_run,
        get_run=get_run,
        thread_factory=thread_factory,
        run_id_factory=lambda: "failed_run_id",
    )

    service.start_run(trigger_source="airflow", requested_by="james")
    created_threads[0].run_now()

    failed = service.get_run("failed_run_id")
    assert failed is not None
    assert failed["status"] == "failed"
    assert failed["error_message"] == "boom"
