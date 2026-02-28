from __future__ import annotations

import datetime as dt
import os
import subprocess
import uuid
from pathlib import Path
from typing import Any

from app.core.config import PROJECT_ROOT, settings
from app.data.mongo import get_collection
from app.data.mongo_data_sync_job_run import (
    create_data_sync_job_run,
    get_data_sync_job_run,
    update_data_sync_job_run,
)

REQUIRED_DAILY_TASKS = [
    "pull_daily",
    "sync_stk_factor_pro",
    "sync_shenwan_daily",
    "sync_zhishu_data",
]
WEEKLY_TASKS = ["sync_shenwan_members", "compact_parquet"]

_JOB_PROCESSES: dict[str, subprocess.Popen[Any]] = {}


def normalize_ymd(value: str) -> str:
    text = str(value or "").strip().replace("-", "")
    if len(text) != 8 or not text.isdigit():
        raise ValueError("invalid date, use YYYYMMDD or YYYY-MM-DD")
    return text


def _parse_ymd(value: str) -> dt.date:
    return dt.datetime.strptime(value, "%Y%m%d").date()


def _build_trade_calendar_range(start_date: str, end_date: str) -> list[dict[str, Any]]:
    collection = get_collection("trade_calendar")
    cursor = collection.find(
        {
            "exchange": "SSE",
            "cal_date": {"$gte": start_date, "$lte": end_date},
        },
        {"_id": 0, "cal_date": 1, "is_open": 1},
    ).sort("cal_date", 1)
    return list(cursor)


def _build_sync_task_map(start_date: str, end_date: str) -> dict[str, set[str]]:
    collection = get_collection("data_sync_date")
    cursor = collection.find(
        {"trade_date": {"$gte": start_date, "$lte": end_date}},
        {"_id": 0, "trade_date": 1, "task": 1},
    )
    task_map: dict[str, set[str]] = {}
    for row in cursor:
        trade_date = str(row.get("trade_date") or "")
        task = str(row.get("task") or "")
        if not trade_date or not task:
            continue
        task_map.setdefault(trade_date, set()).add(task)
    return task_map


def get_calendar_status(start_date: str, end_date: str) -> dict[str, Any]:
    start = normalize_ymd(start_date)
    end = normalize_ymd(end_date)
    if start > end:
        raise ValueError("start_date cannot be after end_date")

    calendar_rows = _build_trade_calendar_range(start, end)
    task_map = _build_sync_task_map(start, end)

    items: list[dict[str, Any]] = []
    summary = {
        "trading_days": 0,
        "synced_all_required": 0,
        "partially_synced": 0,
        "missing": 0,
        "non_trading": 0,
    }

    required_set = set(REQUIRED_DAILY_TASKS)
    weekly_set = set(WEEKLY_TASKS)

    for row in calendar_rows:
        trade_date = str(row.get("cal_date") or "")
        is_open = str(row.get("is_open") or "") == "1"
        completed_tasks = sorted(task_map.get(trade_date, set()))

        status = "non_trading"
        missing_tasks: list[str] = []
        if not is_open:
            summary["non_trading"] += 1
        else:
            summary["trading_days"] += 1
            completed_required = required_set.intersection(completed_tasks)
            missing_tasks = sorted(required_set.difference(completed_required))
            if not missing_tasks:
                status = "synced_all_required"
                summary["synced_all_required"] += 1
            elif len(completed_required) > 0:
                status = "partially_synced"
                summary["partially_synced"] += 1
            else:
                status = "missing"
                summary["missing"] += 1

        items.append(
            {
                "trade_date": trade_date,
                "is_open": is_open,
                "status": status,
                "completed_tasks": completed_tasks,
                "completed_required_tasks": sorted(required_set.intersection(completed_tasks)),
                "completed_weekly_tasks": sorted(weekly_set.intersection(completed_tasks)),
                "missing_required_tasks": missing_tasks,
            }
        )

    return {
        "start_date": start,
        "end_date": end,
        "required_tasks": REQUIRED_DAILY_TASKS,
        "weekly_tasks": WEEKLY_TASKS,
        "summary": summary,
        "items": items,
    }


def get_missing_dates(start_date: str, end_date: str) -> dict[str, Any]:
    calendar = get_calendar_status(start_date, end_date)
    missing_items = [
        {
            "trade_date": item["trade_date"],
            "status": item["status"],
            "missing_required_tasks": item["missing_required_tasks"],
            "completed_required_tasks": item["completed_required_tasks"],
        }
        for item in calendar["items"]
        if item["is_open"] and item["status"] in {"missing", "partially_synced"}
    ]
    return {
        "start_date": calendar["start_date"],
        "end_date": calendar["end_date"],
        "required_tasks": calendar["required_tasks"],
        "total_missing_dates": len(missing_items),
        "items": missing_items,
    }


def _get_script_path() -> Path:
    this_file = Path(__file__).resolve()
    candidates = [
        PROJECT_ROOT / "backend" / "scripts" / "daily" / "docker-daily.sh",
        PROJECT_ROOT / "scripts" / "daily" / "docker-daily.sh",
        Path("/app") / "scripts" / "daily" / "docker-daily.sh",
        PROJECT_ROOT / "backend" / "scripts" / "daily" / "daily.sh",
        PROJECT_ROOT / "scripts" / "daily" / "daily.sh",
        Path("/app") / "scripts" / "daily" / "daily.sh",
        this_file.parents[3] / "backend" / "scripts" / "daily" / "daily.sh",
        this_file.parents[2] / "scripts" / "daily" / "daily.sh",
    ]
    for path in candidates:
        if path.exists():
            return path
    raise RuntimeError(f"daily.sh not found: {candidates[0]}")


def create_sync_job(*, start_date: str, end_date: str, created_by: str) -> dict[str, Any]:
    start = normalize_ymd(start_date)
    end = normalize_ymd(end_date)
    if start > end:
        raise ValueError("start_date cannot be after end_date")
    start_dt = _parse_ymd(start)
    end_dt = _parse_ymd(end)
    span_days = (end_dt - start_dt).days + 1
    if span_days > 5:
        raise ValueError("date range cannot exceed 5 days")

    job_id = uuid.uuid4().hex
    log_dir_candidates = [
        settings.log_dir / "data_sync",
        PROJECT_ROOT / "logs" / "data_sync",
        Path("/tmp") / "freedom" / "logs" / "data_sync",
    ]
    log_dir: Path | None = None
    log_dir_err: Exception | None = None
    for candidate in log_dir_candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            log_dir = candidate
            break
        except Exception as exc:
            log_dir_err = exc
            continue
    if log_dir is None:
        raise RuntimeError(f"failed to prepare log directory: {log_dir_err}")
    log_file = log_dir / f"{job_id}.log"

    create_data_sync_job_run(
        job_id=job_id,
        start_date=start,
        end_date=end,
        created_by=str(created_by or ""),
        log_file=str(log_file),
        status="pending",
    )

    script_path = _get_script_path()
    project_root = script_path.parents[3] if len(script_path.parents) >= 4 else PROJECT_ROOT
    cmd = [
        "bash",
        str(script_path),
        "--start-date",
        start,
        "--end-date",
        end,
    ]
    now = dt.datetime.now(dt.UTC)
    try:
        fh = open(log_file, "ab")
        process = subprocess.Popen(
            cmd,
            cwd=str(project_root),
            stdout=fh,
            stderr=subprocess.STDOUT,
        )
        fh.close()
        _JOB_PROCESSES[job_id] = process
        update_data_sync_job_run(
            job_id=job_id,
            status="running",
            pid=process.pid,
            started_at=now,
            error_message="",
        )
    except Exception as exc:
        update_data_sync_job_run(
            job_id=job_id,
            status="failed",
            error_message=str(exc),
            finished_at=now,
            exit_code=-1,
        )
        raise RuntimeError(f"failed to start daily.sh: {exc}") from exc

    row = get_data_sync_job_run(job_id)
    if not row:
        raise RuntimeError("job created but cannot load record")
    return row


def _refresh_running_status(job_id: str, row: dict[str, Any]) -> dict[str, Any]:
    if row.get("status") != "running":
        return row

    process = _JOB_PROCESSES.get(job_id)
    now = dt.datetime.now(dt.UTC)
    if process is not None:
        rc = process.poll()
        if rc is None:
            return row
        status = "success" if rc == 0 else "failed"
        update_data_sync_job_run(job_id=job_id, status=status, exit_code=rc, finished_at=now)
        _JOB_PROCESSES.pop(job_id, None)
        updated = get_data_sync_job_run(job_id)
        return updated or row

    pid = row.get("pid")
    if pid:
        try:
            os.kill(int(pid), 0)
            return row
        except ProcessLookupError:
            update_data_sync_job_run(
                job_id=job_id,
                status="failed",
                exit_code=-1,
                finished_at=now,
                error_message="process not found; state unknown",
            )
            updated = get_data_sync_job_run(job_id)
            return updated or row
        except PermissionError:
            return row
    return row


def get_sync_job(job_id: str) -> dict[str, Any] | None:
    row = get_data_sync_job_run(job_id)
    if not row:
        return None
    return _refresh_running_status(job_id, row)


def get_sync_job_logs(job_id: str, offset: int = 0, limit: int = 200_000) -> dict[str, Any]:
    row = get_sync_job(job_id)
    if not row:
        raise ValueError("job not found")

    log_file = str(row.get("log_file") or "")
    if not log_file:
        return {"job_id": job_id, "offset": offset, "next_offset": offset, "content": "", "eof": True}

    path = Path(log_file)
    if not path.exists():
        return {"job_id": job_id, "offset": offset, "next_offset": offset, "content": "", "eof": True}

    size = path.stat().st_size
    safe_offset = max(0, min(int(offset), size))
    safe_limit = max(1, min(int(limit), 1_000_000))
    with path.open("rb") as fh:
        fh.seek(safe_offset)
        chunk = fh.read(safe_limit)
    content = chunk.decode("utf-8", errors="replace")
    next_offset = safe_offset + len(chunk)
    eof = next_offset >= size and row.get("status") in {"success", "failed"}
    return {
        "job_id": job_id,
        "status": row.get("status"),
        "offset": safe_offset,
        "next_offset": next_offset,
        "content": content,
        "eof": eof,
    }


def stop_sync_job(job_id: str) -> dict[str, Any]:
    row = get_data_sync_job_run(job_id)
    if not row:
        raise ValueError("job not found")

    status = str(row.get("status") or "")
    if status in {"success", "failed", "cancelled"}:
        return row

    now = dt.datetime.now(dt.UTC)
    pid = row.get("pid")
    stopped = False
    if pid:
        try:
            os.kill(int(pid), 15)
            stopped = True
        except ProcessLookupError:
            stopped = True
        except PermissionError:
            pass
        except Exception:
            pass

    process = _JOB_PROCESSES.pop(job_id, None)
    if process is not None:
        try:
            process.terminate()
            stopped = True
        except Exception:
            pass

    update_data_sync_job_run(
        job_id=job_id,
        status="cancelled",
        exit_code=-15 if stopped else -1,
        error_message="terminated by user",
        finished_at=now,
    )
    updated = get_data_sync_job_run(job_id)
    if not updated:
        raise ValueError("job not found")
    return updated

