from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from airflow.models.dagrun import DagRun

from app.airflow_sync.daily_sync_registry import DAILY_SYNC_TASKS
from app.airflow_sync.feishu_alert import send_feishu_alert


_ALERT_SENT_FILE = Path(
    os.getenv("FREEDOM_ALERT_SENT_FILE", "/opt/airflow/alerts/sent_alerts.json")
)

# Build a lookup of critical task IDs from the daily sync registry
_CRITICAL_TASK_IDS: set[str] = {
    task.task_id for task in DAILY_SYNC_TASKS if task.critical
}

# DAGs that are NOT the market data DAG — any failure in these should alert
_ALWAYS_ALERT_DAGS: set[str] = {
    "freedom_agent_daily_v1",
    "freedom_data_integrity_weekly",
}


def _load_sent_alerts() -> dict[str, str]:
    """Load the deduplication map {dag_id#run_id: timestamp}."""
    if not _ALERT_SENT_FILE.exists():
        return {}
    try:
        with open(_ALERT_SENT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_sent_alerts(sent: dict[str, str]) -> None:
    """Atomically write the deduplication map."""
    _ALERT_SENT_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(_ALERT_SENT_FILE.parent),
        prefix="sent_alerts_",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(sent, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, _ALERT_SENT_FILE)
    except Exception:
        # If atomic write fails, fall back to direct write
        with open(_ALERT_SENT_FILE, "w", encoding="utf-8") as f:
            json.dump(sent, f, ensure_ascii=False, indent=2)
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _should_alert(dag_id: str, run_id: str) -> bool:
    """Check whether an alert has already been sent for this dag+run."""
    sent = _load_sent_alerts()
    key = f"{dag_id}#{run_id}"
    return key not in sent


def _mark_alert_sent(dag_id: str, run_id: str) -> None:
    """Record that an alert was sent for this dag+run."""
    sent = _load_sent_alerts()
    key = f"{dag_id}#{run_id}"
    sent[key] = datetime.now(tz=timezone.utc).isoformat()
    _save_sent_alerts(sent)


def _collect_failed_tasks(dag_run: Any) -> list[str]:
    """Return a sorted list of task IDs that are in FAILED state."""
    failed: list[str] = []
    try:
        for ti in dag_run.get_task_instances():
            if str(ti.state).upper() == "FAILED":
                failed.append(ti.task_id)
    except Exception:
        pass
    return sorted(failed)


def _is_critical_failure(dag_id: str, failed_tasks: list[str]) -> bool:
    """Determine whether the failure warrants an immediate alert.

    Rules:
    1. For DAGs in _ALWAYS_ALERT_DAGS, any failure is critical.
    2. For freedom_market_data_daily, only critical-task failures are critical.
    3. For unknown DAGs, any failure is treated as critical (safe default).
    """
    if dag_id in _ALWAYS_ALERT_DAGS:
        return bool(failed_tasks)

    if dag_id == "freedom_market_data_daily":
        return any(task_id in _CRITICAL_TASK_IDS for task_id in failed_tasks)

    # Unknown DAG — alert on any failure to be safe
    return bool(failed_tasks)


def _build_alert_message(
    dag_id: str,
    run_id: str,
    execution_date: str,
    failed_tasks: list[str],
) -> str:
    """Build human-readable alert content."""
    critical_failed = [
        t for t in failed_tasks if t in _CRITICAL_TASK_IDS
    ]
    lines: list[str] = [
        f"DAG: {dag_id}",
        f"Run ID: {run_id}",
        f"执行日期: {execution_date}",
        f"告警时间: {datetime.now(tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        "",
    ]
    if critical_failed:
        lines.append(f"关键失败任务: {', '.join(critical_failed)}")
    if failed_tasks:
        lines.append(f"所有失败任务: {', '.join(failed_tasks)}")
    lines.append("")
    lines.append("请尽快检查！")
    return "\n".join(lines)


def _collect_task_summary(dag_run: Any) -> dict[str, int]:
    """Count task states for a completed DAG run."""
    counts: dict[str, int] = {"success": 0, "failed": 0, "skipped": 0}
    try:
        for ti in dag_run.get_task_instances():
            state = str(ti.state or "").lower()
            if state in counts:
                counts[state] += 1
    except Exception:
        pass
    return counts


def _build_success_message(
    dag_id: str,
    run_id: str,
    execution_date: str,
    counts: dict[str, int],
) -> str:
    """Build human-readable success notification content."""
    lines: list[str] = [
        f"DAG: {dag_id}",
        f"Run ID: {run_id}",
        f"执行日期: {execution_date}",
        f"完成时间: {datetime.now(tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        "",
        f"任务统计: 成功 {counts['success']} / 失败 {counts['failed']} / 跳过 {counts['skipped']}",
    ]
    return "\n".join(lines)


def on_dag_failure_alert(context: dict[str, Any]) -> None:
    """Airflow DAG ``on_failure_callback``.

    Sends at most one Feishu alert per DAG Run.
    Only alerts when a critical (or always-alert) failure is detected.
    """
    dag_run = context["dag_run"]
    dag_id = str(dag_run.dag_id)
    run_id = str(dag_run.run_id)
    execution_date = str(context.get("ds") or "")

    # Deduplication: one alert per DAG Run
    if not _should_alert(dag_id, run_id):
        print(f"[AirflowAlert] Alert already sent for {dag_id} run={run_id}, skipping.")
        return

    failed_tasks = _collect_failed_tasks(dag_run)

    if not _is_critical_failure(dag_id, failed_tasks):
        print(
            f"[AirflowAlert] Non-critical failure in {dag_id} run={run_id}, "
            f"tasks={failed_tasks}. Not alerting."
        )
        _mark_alert_sent(dag_id, run_id)
        return

    title = f"Airflow DAG 失败告警"
    content = _build_alert_message(dag_id, run_id, execution_date, failed_tasks)

    print(f"[AirflowAlert] Sending alert for {dag_id} run={run_id}")
    try:
        resp = send_feishu_alert(title, content)
        print(f"[AirflowAlert] Feishu response: {resp}")
    except Exception as e:
        print(f"[AirflowAlert] Failed to send Feishu alert: {e}")
        # Don't mark as sent so it can retry on next callback invocation
        return

    _mark_alert_sent(dag_id, run_id)


def on_dag_success_alert(context: dict[str, Any]) -> None:
    """Airflow DAG ``on_success_callback``.

    Sends at most one Feishu notification per DAG Run when all tasks succeed.
    """
    dag_run = context["dag_run"]
    dag_id = str(dag_run.dag_id)
    run_id = str(dag_run.run_id)
    execution_date = str(context.get("ds") or "")

    # Deduplication: one alert per DAG Run
    if not _should_alert(dag_id, run_id):
        print(f"[AirflowAlert] Success alert already sent for {dag_id} run={run_id}, skipping.")
        return

    counts = _collect_task_summary(dag_run)

    title = f"Airflow DAG 执行完成"
    content = _build_success_message(dag_id, run_id, execution_date, counts)

    print(f"[AirflowAlert] Sending success alert for {dag_id} run={run_id}")
    try:
        resp = send_feishu_alert(title, content)
        print(f"[AirflowAlert] Feishu response: {resp}")
    except Exception as e:
        print(f"[AirflowAlert] Failed to send Feishu success alert: {e}")
        return

    _mark_alert_sent(dag_id, run_id)
