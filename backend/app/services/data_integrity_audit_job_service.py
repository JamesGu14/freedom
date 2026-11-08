"""Async job service for triggering data integrity audits via subprocess.

Why subprocess (not threads)?
-----------------------------
The previous implementation ran ``run_audit`` inside a daemon thread inside
the Gunicorn worker that handled the HTTP request. When Gunicorn OOM-killed
the worker (or recycled it via ``max_requests``), the thread died without
writing a terminal status, leaving MongoDB records stuck at ``running``
forever.

This version spawns the audit as an independent process via
``subprocess.Popen(start_new_session=True)``. The child process is fully
detached from the Gunicorn worker lifecycle and runs the standalone CLI
runner (``scripts.audit.run_data_integrity_audit_runner``). The CLI runner
is responsible for writing ``running`` -> ``succeeded``/``failed`` state
transitions, including a SIGTERM handler so graceful termination still
writes a terminal state.

Watchdog
--------
Even with subprocess isolation, two scenarios can still strand records:
- ``SIGKILL`` cannot be caught (host OOM, ``kill -9``).
- Host crash / power loss.

``_cleanup_stale_runs`` is invoked from both ``start_run`` and ``get_run``
to lazily reap any record whose ``started_at`` exceeds
``stale_timeout_seconds``. This guarantees that any orphaned ``running``
record will eventually be marked ``failed``, allowing clients (Airflow
poll loop) to see a terminal state and retry / alert.
"""

from __future__ import annotations

import datetime as dt
import logging
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Callable

from app.audit.models import AuditRunResult
from app.core.config import settings
from app.data.mongo_data_integrity_audit import (
    get_data_integrity_audit_run,
    upsert_data_integrity_audit_run,
)
from app.data.mongo import get_collection
from scripts.audit.run_data_integrity_audit import build_run_id, run_audit

logger = logging.getLogger(__name__)


AuditRunner = Callable[..., AuditRunResult]
UpsertRun = Callable[[dict[str, Any]], None]
GetRun = Callable[[str], dict[str, Any] | None]
ProcessSpawner = Callable[..., Any]
StaleCleanup = Callable[[int], int]


DEFAULT_STALE_TIMEOUT_SECONDS = 30 * 60
_RUNNER_MODULE = "scripts.audit.run_data_integrity_audit_runner"


def _now_utc() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def default_stale_cleanup(timeout_seconds: int) -> int:
    """Mark any audit run stuck in ``running``/``queued`` past ``timeout_seconds`` as ``failed``.

    Returns the number of records reaped. Safe to call from any process;
    uses MongoDB atomic ``update_many`` so concurrent cleanups are idempotent.
    """
    cutoff = _now_utc() - dt.timedelta(seconds=timeout_seconds)
    result = get_collection("data_integrity_audit_runs").update_many(
        {
            "status": {"$in": ["running", "queued"]},
            "$or": [
                {"started_at": {"$lt": cutoff}},
                {"started_at": None, "queued_at": {"$lt": cutoff}},
                {"started_at": None, "queued_at": None, "created_at": {"$lt": cutoff}},
            ],
        },
        {
            "$set": {
                "status": "failed",
                "error_message": (
                    f"watchdog: audit process did not complete within {timeout_seconds}s "
                    "(likely killed by OOM, host crash, or ungraceful termination)"
                ),
                "finished_at": _now_utc(),
                "updated_at": _now_utc(),
            }
        },
    )
    return int(result.modified_count)


def _default_process_spawner(cmd: list[str], **popen_kwargs: Any) -> subprocess.Popen:
    """Default subprocess spawner. Thin wrapper around ``subprocess.Popen`` for testability."""
    return subprocess.Popen(cmd, **popen_kwargs)  # noqa: S603
    # cmd is constructed internally from typed parameters, not from user input.


def _build_runner_command(
    *,
    run_id: str,
    trigger_source: str,
    scheduled_for: str | None,
    selected_datasets: list[str],
    start_date: str | None,
    end_date: str | None,
) -> list[str]:
    """Build the CLI invocation for the standalone audit runner."""
    cmd: list[str] = [sys.executable, "-m", _RUNNER_MODULE, "--run-id", run_id, "--trigger-source", trigger_source]
    if scheduled_for:
        cmd.extend(["--scheduled-for", scheduled_for])
    if selected_datasets:
        cmd.extend(["--datasets", ",".join(selected_datasets)])
    if start_date:
        cmd.extend(["--start-date", start_date])
    if end_date:
        cmd.extend(["--end-date", end_date])
    return cmd


def _open_runner_log(run_id: str):
    """Open (or create) the runner log file for append-mode binary writes."""
    log_dir = settings.log_dir / "data_audit" / run_id
    log_dir.mkdir(parents=True, exist_ok=True)
    return open(log_dir / "runner.log", "ab")


class DataIntegrityAuditJobService:
    """Async orchestrator for data integrity audit runs.

    Responsibilities:
    1. Reap stale ``running`` records via ``_cleanup_stale_runs``.
    2. Create a ``queued`` MongoDB record.
    3. Spawn the audit CLI runner as a detached subprocess.
    4. Surface run status via ``get_run`` (also reaps stale records first).

    This service does NOT execute the audit itself — that lives in
    ``scripts.audit.run_data_integrity_audit_runner``. Cross-process isolation
    is the entire point.
    """

    def __init__(
        self,
        *,
        audit_runner: AuditRunner = run_audit,  # deprecated, retained for backward compat
        upsert_run: UpsertRun = upsert_data_integrity_audit_run,
        get_run: GetRun = get_data_integrity_audit_run,
        thread_factory: Any = None,  # deprecated, ignored; kept for backward compat
        process_spawner: ProcessSpawner | None = None,
        stale_cleanup_fn: StaleCleanup | None = None,
        stale_timeout_seconds: int = DEFAULT_STALE_TIMEOUT_SECONDS,
        run_id_factory: Callable[[], str] | None = None,
    ) -> None:
        del audit_runner, thread_factory  # acknowledged but unused
        self._upsert_run = upsert_run
        self._get_run = get_run
        self._process_spawner = process_spawner or _default_process_spawner
        self._stale_cleanup_fn = stale_cleanup_fn or default_stale_cleanup
        self._stale_timeout_seconds = stale_timeout_seconds
        self._run_id_factory = run_id_factory or self._default_run_id
        self._run_lock = threading.Lock()
        self._active_run_id: str | None = None

    def _cleanup_stale_runs(self) -> int:
        try:
            return self._stale_cleanup_fn(self._stale_timeout_seconds)
        except Exception:
            logger.exception("stale cleanup failed; continuing")
            return 0

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
        self._cleanup_stale_runs()

        with self._run_lock:
            if self._active_run_id is not None:
                existing = self._get_run(self._active_run_id)
                if existing is not None and existing.get("status") in {"queued", "running"}:
                    return _serialize_record(existing)
                self._active_run_id = None

            run_id = self._run_id_factory()
            # Persist before publishing the pointer, under the same lock, so
            # concurrent requests cannot mistake a pending insert for a stale run.
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
                    "queued_at": _now_utc(),
                    "error_message": "",
                }
            )
            self._active_run_id = run_id

        cmd = _build_runner_command(
            run_id=run_id,
            trigger_source=str(trigger_source or "manual"),
            scheduled_for=scheduled_for,
            selected_datasets=list(selected_datasets or []),
            start_date=start_date,
            end_date=end_date,
        )

        try:
            runner_env = os.environ.copy()
            backend_root = str(Path(__file__).resolve().parents[2])
            runner_env["PYTHONPATH"] = os.pathsep.join(
                part for part in (backend_root, runner_env.get("PYTHONPATH", "")) if part
            )
            with _open_runner_log(run_id) as log_file:
                self._process_spawner(
                    cmd,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    start_new_session=True,
                    close_fds=True,
                    env=runner_env,
                )
        except Exception as exc:
            logger.exception("failed to spawn audit subprocess for run_id=%s", run_id)
            self._upsert_run(
                {
                    "run_id": run_id,
                    "status": "failed",
                    "finished_at": _now_utc(),
                    "error_message": f"failed to spawn audit subprocess: {type(exc).__name__}: {exc}",
                }
            )
            with self._run_lock:
                if self._active_run_id == run_id:
                    self._active_run_id = None
            raise

        # Use _get_run (not get_run) to avoid invoking stale cleanup a second time
        # — the record we just wrote cannot possibly be stale yet.
        record = self._get_run(run_id)
        if record:
            return _serialize_record(record)
        return {"run_id": run_id, "status": "queued"}

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        self._cleanup_stale_runs()
        record = self._get_run(run_id)
        if not record:
            return None
        return _serialize_record(record)

    def _default_run_id(self) -> str:
        return f"async_{build_run_id()}"


def _build_status_summary(result: AuditRunResult) -> dict[str, int]:
    """Deprecated; kept for backward compatibility. Use ``app.audit.summary_builder.build_status_summary``."""
    from app.audit.summary_builder import build_status_summary

    return build_status_summary(result)


def _build_dataset_summary(result: AuditRunResult) -> list[dict[str, Any]]:
    """Deprecated; kept for backward compatibility. Use ``app.audit.summary_builder.build_dataset_summary``."""
    from app.audit.summary_builder import build_dataset_summary

    return build_dataset_summary(result)


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
