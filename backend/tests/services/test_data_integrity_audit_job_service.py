from __future__ import annotations

import datetime as dt
import subprocess

import pytest

from app.services.data_integrity_audit_job_service import DataIntegrityAuditJobService


@pytest.fixture(autouse=True)
def isolate_runner_logs(monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.data_integrity_audit_job_service.settings.log_dir", tmp_path)


class _FakeProcess:
    """Test double for subprocess.Popen.

    Records the spawn command and kwargs. Does NOT execute the audit — that is
    the CLI runner's responsibility and is tested separately in
    ``tests/audit/test_data_integrity_audit_runner_cli.py``.
    """

    def __init__(self) -> None:
        self.returncode: int | None = None
        self.cmd: list[str] | None = None
        self.kwargs: dict[str, object] = {}
        self.poll_count = 0

    def poll(self) -> int | None:
        self.poll_count += 1
        return self.returncode

    def wait(self, timeout: float | None = None) -> int:  # noqa: ARG002
        return self.returncode or 0


def _make_fake_spawner(processes: list[_FakeProcess]):
    def spawner(cmd: list[str], **kwargs):  # noqa: ANN003
        process = _FakeProcess()
        process.cmd = list(cmd)
        process.kwargs = dict(kwargs)
        processes.append(process)
        return process

    return spawner


def _make_in_memory_store():
    store: dict[str, dict[str, object]] = {}

    def upsert_run(record: dict[str, object]) -> None:
        current = dict(store.get(str(record["run_id"]), {}))
        current.update(record)
        store[str(record["run_id"])] = current

    def get_run(run_id: str) -> dict[str, object] | None:
        record = store.get(run_id)
        return dict(record) if record else None

    return store, upsert_run, get_run


# ---------- start_run: spawns subprocess and writes queued record ----------


def test_start_run_creates_queued_record_and_spawns_process() -> None:
    store, upsert_run, get_run = _make_in_memory_store()
    spawned: list[_FakeProcess] = []

    service = DataIntegrityAuditJobService(
        upsert_run=upsert_run,
        get_run=get_run,
        process_spawner=_make_fake_spawner(spawned),
        stale_cleanup_fn=lambda timeout_seconds: 0,
        run_id_factory=lambda: "gen_run_001",
    )

    result = service.start_run(
        trigger_source="airflow_weekly",
        requested_by="james",
        scheduled_for="2026-07-26T06:00:00+08:00",
    )

    assert result["run_id"] == "gen_run_001"
    assert result["status"] == "queued"
    assert result["trigger_source"] == "airflow_weekly"

    persisted = store["gen_run_001"]
    assert persisted["status"] == "queued"
    assert persisted["scheduled_for"] == "2026-07-26T06:00:00+08:00"

    assert len(spawned) == 1
    cmd = spawned[0].cmd
    assert cmd is not None
    assert "-m" in cmd
    assert "scripts.audit.run_data_integrity_audit_runner" in cmd
    assert "--run-id" in cmd
    assert "gen_run_001" in cmd
    assert "--trigger-source" in cmd
    assert "airflow_weekly" in cmd
    # scheduled_for is forwarded
    assert "--scheduled-for" in cmd
    # kwargs detach from parent process group
    assert spawned[0].kwargs.get("start_new_session") is True
    assert spawned[0].kwargs.get("stdin") == subprocess.DEVNULL  # type: ignore[name-defined]


def test_start_run_forwards_dataset_filter_and_dates_to_subprocess() -> None:
    _, upsert_run, get_run = _make_in_memory_store()
    spawned: list[_FakeProcess] = []

    service = DataIntegrityAuditJobService(
        upsert_run=upsert_run,
        get_run=get_run,
        process_spawner=_make_fake_spawner(spawned),
        stale_cleanup_fn=lambda timeout_seconds: 0,
        run_id_factory=lambda: "filtered_run",
    )

    service.start_run(
        trigger_source="manual",
        requested_by="james",
        selected_datasets=["daily", "daily_basic"],
        start_date="20240101",
        end_date="20241231",
    )

    cmd = spawned[0].cmd
    assert cmd is not None
    datasets_idx = cmd.index("--datasets")
    assert cmd[datasets_idx + 1] == "daily,daily_basic"
    assert cmd[cmd.index("--start-date") + 1] == "20240101"
    assert cmd[cmd.index("--end-date") + 1] == "20241231"


def test_start_run_marks_failed_when_subprocess_spawn_raises() -> None:
    store, upsert_run, get_run = _make_in_memory_store()

    def exploding_spawner(cmd, **kwargs):  # noqa: ANN001, ARG001
        raise OSError("cannot fork")

    service = DataIntegrityAuditJobService(
        upsert_run=upsert_run,
        get_run=get_run,
        process_spawner=exploding_spawner,
        stale_cleanup_fn=lambda timeout_seconds: 0,
        run_id_factory=lambda: "boom_run",
    )

    with pytest.raises(OSError, match="cannot fork"):
        service.start_run(trigger_source="manual", requested_by="james")

    persisted = store["boom_run"]
    assert persisted["status"] == "failed"
    assert "cannot fork" in str(persisted.get("error_message", ""))


def test_start_run_returns_active_run_when_one_is_already_in_progress() -> None:
    _, upsert_run, get_run = _make_in_memory_store()
    spawned: list[_FakeProcess] = []

    service = DataIntegrityAuditJobService(
        upsert_run=upsert_run,
        get_run=get_run,
        process_spawner=_make_fake_spawner(spawned),
        stale_cleanup_fn=lambda timeout_seconds: 0,
        run_id_factory=lambda: "first_run",
    )

    first = service.start_run(trigger_source="airflow", requested_by="james")

    # second start_run while first is still active should return the active run
    second = service.start_run(trigger_source="airflow", requested_by="james")

    assert second["run_id"] == first["run_id"] == "first_run"
    assert len(spawned) == 1, "second start_run should NOT spawn a new process"


@pytest.mark.parametrize("terminal_status", ["succeeded", "failed"])
def test_start_run_starts_again_after_previous_run_finishes(terminal_status) -> None:
    store, upsert_run, get_run = _make_in_memory_store()
    spawned: list[_FakeProcess] = []
    run_ids = iter(["first", "second"])
    service = DataIntegrityAuditJobService(
        upsert_run=upsert_run,
        get_run=get_run,
        process_spawner=_make_fake_spawner(spawned),
        stale_cleanup_fn=lambda _: 0,
        run_id_factory=lambda: next(run_ids),
    )
    service.start_run(trigger_source="manual", requested_by="james")
    store["first"]["status"] = terminal_status

    result = service.start_run(trigger_source="manual", requested_by="james")

    assert result["run_id"] == "second"
    assert result["status"] == "queued"
    assert len(spawned) == 2


def test_spawned_runner_can_import_from_arbitrary_working_directory(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PYTHONPATH", raising=False)
    _, upsert_run, get_run = _make_in_memory_store()

    def probe_spawner(cmd, **kwargs):
        # --help loads the real CLI without starting an audit or touching MongoDB.
        subprocess.run([*cmd, "--help"], check=True, timeout=20, **kwargs)

    service = DataIntegrityAuditJobService(
        upsert_run=upsert_run,
        get_run=get_run,
        process_spawner=probe_spawner,
        stale_cleanup_fn=lambda _: 0,
        run_id_factory=lambda: "import_probe",
    )

    assert service.start_run(trigger_source="manual", requested_by="james")["status"] == "queued"
    assert "--run-id" in (tmp_path / "data_audit/import_probe/runner.log").read_text()


# ---------- stale cleanup ----------


def test_stale_cleanup_marks_old_running_records_as_failed() -> None:
    cleanup_calls: list[int] = []

    def fake_cleanup(timeout_seconds: int) -> int:
        cleanup_calls.append(timeout_seconds)
        return 3

    _, upsert_run, get_run = _make_in_memory_store()

    service = DataIntegrityAuditJobService(
        upsert_run=upsert_run,
        get_run=get_run,
        process_spawner=_make_fake_spawner([]),
        stale_cleanup_fn=fake_cleanup,
        stale_timeout_seconds=42 * 60,
        run_id_factory=lambda: "r",
    )

    service.start_run(trigger_source="airflow", requested_by="james")

    assert cleanup_calls == [42 * 60], "start_run must invoke cleanup with configured timeout"


def test_get_run_invokes_stale_cleanup_before_returning() -> None:
    cleanup_calls: list[int] = []
    _, upsert_run, get_run = _make_in_memory_store()
    get_run("any")  # ensure store callable works

    service = DataIntegrityAuditJobService(
        upsert_run=upsert_run,
        get_run=get_run,
        process_spawner=_make_fake_spawner([]),
        stale_cleanup_fn=lambda timeout_seconds: cleanup_calls.append(timeout_seconds) or 0,
        run_id_factory=lambda: "r",
    )

    # First start_run already triggers cleanup once
    service.start_run(trigger_source="airflow", requested_by="james")
    cleanup_calls.clear()

    # get_run should also trigger cleanup
    service.get_run("whatever")

    assert cleanup_calls == [30 * 60], "get_run must invoke cleanup with default timeout"


def test_default_stale_cleanup_writes_failed_status_for_old_records() -> None:
    """Integration check for the default cleanup implementation.

    Verifies the real cleanup writes the expected MongoDB update_many payload
    by injecting a fake collection.
    """
    import app.services.data_integrity_audit_job_service as service_module

    captured: dict[str, object] = {}

    class _FakeCollection:
        def update_many(self, query, update):
            captured["query"] = query
            captured["update"] = update

            class _Result:
                modified_count = 1

            return _Result()

    def fake_get_collection(name):  # noqa: ARG001
        return _FakeCollection()

    original = service_module.get_collection
    service_module.get_collection = fake_get_collection  # type: ignore[assignment]
    try:
        cleanup = service_module.default_stale_cleanup(timeout_seconds=15 * 60)
    finally:
        service_module.get_collection = original  # type: ignore[assignment]

    assert cleanup == 1
    query = captured["query"]
    assert query["status"] == {"$in": ["running", "queued"]}
    # Started runs use started_at; never-started runs fall back to queued_at,
    # then created_at for records written before queued_at was introduced.
    clauses = query["$or"]
    assert any("$lt" in clause.get("started_at", {}) for clause in clauses)
    assert any(clause.get("started_at") is None and "$lt" in clause.get("queued_at", {}) for clause in clauses)
    assert any(
        clause.get("started_at") is None and clause.get("queued_at") is None
        and "$lt" in clause.get("created_at", {}) for clause in clauses
    )
    update = captured["update"]
    assert update["$set"]["status"] == "failed"
    assert "watchdog" in update["$set"]["error_message"]
    assert "finished_at" in update["$set"]
