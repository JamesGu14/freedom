"""CLI entry point for executing a single data integrity audit as a standalone process.

Invocation patterns
-------------------
This runner is invoked in two contexts:

1. **Airflow weekly DAG** (preferred): the Airflow worker SSHes into the host
   and runs this module via ``run_freedom_sync_job.sh``, which sets up the
   ``freedom`` conda env and ``backend/.env``. The host process is fully
   decoupled from the Freedom backend Gunicorn worker lifecycle, so an OOM
   kill of the web worker no longer leaves MongoDB records stuck at
   ``running``.

2. **Backend in-process subprocess** (fallback): when the HTTP-triggered
   async path (``/internal/audits/data-integrity/runs``) is used,
   ``DataIntegrityAuditJobService`` spawns this module via
   ``subprocess.Popen(start_new_session=True)`` instead of a daemon thread.

Guarantees
----------
- Always writes a terminal status (``succeeded`` or ``failed``) to MongoDB,
  even when ``run_audit`` raises or the process receives ``SIGTERM``.
- ``SIGKILL`` cannot be caught; in that case the service-layer watchdog
  (``_cleanup_stale_runs``) reaps the orphaned ``running`` record after
  ``stale_timeout_seconds``.
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import signal
import sys
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable

from app.audit.models import AuditRunResult
from app.audit.summary_builder import build_dataset_summary, build_status_summary
from app.data.mongo_data_integrity_audit import upsert_data_integrity_audit_run
from scripts.audit.run_data_integrity_audit import run_audit

logger = logging.getLogger(__name__)


def _now_utc() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


@dataclass
class RunnerArgs:
    """Parsed CLI arguments in a form convenient for ``execute_run``."""

    run_id: str
    trigger_source: str
    scheduled_for: str | None = None
    datasets: list[str] = field(default_factory=list)
    start_date: str | None = None
    end_date: str | None = None
    last_trade_days: int | None = None


def parse_args(argv: list[str] | None = None) -> RunnerArgs:
    parser = argparse.ArgumentParser(
        description="Run a single data integrity audit as a standalone process.",
    )
    parser.add_argument("--run-id", required=True, help="Unique audit run identifier")
    parser.add_argument(
        "--trigger-source",
        required=True,
        help="Who triggered this run (e.g. airflow_weekly, manual, api)",
    )
    parser.add_argument(
        "--scheduled-for",
        default=None,
        help="ISO timestamp the run was scheduled for (informational)",
    )
    parser.add_argument(
        "--datasets",
        default="",
        help="Comma-separated dataset names to audit; empty audits all registered datasets",
    )
    parser.add_argument(
        "--start-date",
        default=None,
        help="Lower date bound (YYYYMMDD or YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end-date",
        default=None,
        help="Upper date bound (YYYYMMDD or YYYY-MM-DD)",
    )
    parser.add_argument(
        "--last-trade-days",
        type=int,
        default=None,
        help="Audit only the last N SSE trading days (overrides --start-date/--end-date)",
    )
    namespace = parser.parse_args(argv)
    if namespace.last_trade_days is not None and namespace.last_trade_days <= 0:
        parser.error("--last-trade-days must be greater than zero")
    datasets = [name.strip() for name in str(namespace.datasets or "").split(",") if name.strip()]
    return RunnerArgs(
        run_id=str(namespace.run_id).strip(),
        trigger_source=str(namespace.trigger_source).strip(),
        scheduled_for=namespace.scheduled_for,
        datasets=datasets,
        start_date=namespace.start_date or None,
        end_date=namespace.end_date or None,
        last_trade_days=namespace.last_trade_days,
    )


def _mark_running(
    *,
    args: RunnerArgs,
    upsert_run: Callable[[dict[str, Any]], None],
) -> None:
    upsert_run(
        {
            "run_id": args.run_id,
            "status": "running",
            "trigger_source": args.trigger_source,
            "scheduled_for": args.scheduled_for,
            "selected_datasets": list(args.datasets),
            "start_date": args.start_date,
            "end_date": args.end_date,
            "started_at": _now_utc(),
            "error_message": "",
        }
    )


def _mark_succeeded(
    *,
    args: RunnerArgs,
    result: AuditRunResult,
    upsert_run: Callable[[dict[str, Any]], None],
) -> None:
    upsert_run(
        {
            "run_id": args.run_id,
            "status": "succeeded",
            "finished_at": _now_utc(),
            "output_dir": result.output_dir,
            "status_summary": build_status_summary(result),
            "datasets": build_dataset_summary(result),
            "summary": {
                "dataset_count": len(result.datasets),
                "excluded_datasets": list(result.excluded_datasets),
                "output_dir": result.output_dir,
            },
            "error_message": "",
        }
    )


def _mark_failed(
    *,
    args: RunnerArgs,
    error_message: str,
    upsert_run: Callable[[dict[str, Any]], None],
) -> None:
    try:
        upsert_run(
            {
                "run_id": args.run_id,
                "status": "failed",
                "finished_at": _now_utc(),
                "error_message": error_message,
            }
        )
    except Exception:
        logger.exception(
            "failed to persist failed-state for run_id=%s; original error: %s",
            args.run_id,
            error_message,
        )


def _resolve_recent_trade_days(n: int) -> tuple[str, str]:
    from app.data.mongo import get_collection
    col = get_collection("trade_calendar")
    today = dt.datetime.now().strftime("%Y%m%d")
    cursor = col.find(
        {"exchange": "SSE", "is_open": {"$in": ["1", 1]}, "cal_date": {"$lte": today}},
        {"_id": 0, "cal_date": 1},
    ).sort("cal_date", -1).limit(n)
    dates = sorted({str(d["cal_date"]) for d in cursor if d.get("cal_date")})
    if not dates:
        raise ValueError("no SSE trading days found in trade_calendar up to today")
    return dates[0], dates[-1]


def _notify_audit_result(result: AuditRunResult, args: RunnerArgs) -> None:
    non_green = [item for item in result.datasets if item.status != "green"]
    total = len(result.datasets)
    has_issues = bool(non_green)

    severity_cn = {"red": "🔴 严重", "yellow": "🟡 警告"}
    lines: list[str] = []
    if has_issues:
        lines.append(f"📊 数据完整性审计：发现 {len(non_green)} 个数据集存在异常（共检查 {total} 个）")
    else:
        lines.append(f"✅ 数据完整性审计通过：{total} 个数据集全部完整，无缺失")

    if args.start_date and args.end_date:
        lines.append(f"审计窗口：{args.start_date} ~ {args.end_date}")
    lines.append(f"run_id：{args.run_id}")
    lines.append("")

    if has_issues:
        severity_order = {"red": 0, "yellow": 1}
        lines.append("异常数据集详情：")
        for item in sorted(non_green, key=lambda x: severity_order.get(x.status, 9)):
            details = []
            if item.date_gap.missing_trade_dates:
                details.append(f"缺失 {len(item.date_gap.missing_trade_dates)} 个交易日")
            if item.coverage_anomalies:
                details.append(f"覆盖异常 {len(item.coverage_anomalies)} 处")
            if item.rowcount_anomalies:
                details.append(f"行数异常 {len(item.rowcount_anomalies)} 处")
            detail_str = f"（{'，'.join(details)}）" if details else ""
            lines.append(f"  {severity_cn.get(item.status, item.status)} {item.dataset}{detail_str}")
        lines.append("")
        lines.append(f"报告目录：{result.output_dir}")

    try:
        from app.airflow_sync.feishu_alert import send_feishu_audit_alert
        resp = send_feishu_audit_alert("\n".join(lines))
        logger.info("feishu audit alert sent: %s", resp)
    except Exception as exc:
        logger.warning("feishu audit alert failed: %s", exc)


def execute_run(
    args: RunnerArgs,
    *,
    audit_runner: Callable[..., AuditRunResult] = run_audit,
    upsert_run: Callable[[dict[str, Any]], None] = upsert_data_integrity_audit_run,
) -> int:
    """Run a single audit and persist state transitions.

    Returns the process exit code: ``0`` on success, ``1`` on failure.
    """
    try:
        if args.last_trade_days is not None:
            if args.last_trade_days <= 0:
                raise ValueError("last_trade_days must be greater than zero")
            start, end = _resolve_recent_trade_days(args.last_trade_days)
            args.start_date = start
            args.end_date = end
            logger.info(
                "last-trade-days=%s resolved to window %s ~ %s",
                args.last_trade_days, start, end,
            )

        _mark_running(args=args, upsert_run=upsert_run)
        result = audit_runner(
            selected_names=args.datasets or None,
            run_id=args.run_id,
            start_date=args.start_date,
            end_date=args.end_date,
        )
        _mark_succeeded(args=args, result=result, upsert_run=upsert_run)
    except Exception as exc:
        error_message = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
        _mark_failed(args=args, error_message=error_message, upsert_run=upsert_run)
        return 1

    _notify_audit_result(result, args)
    return 0


def _install_signal_handlers(args: RunnerArgs, upsert_run: Callable[[dict[str, Any]], None]) -> None:
    """Best-effort: mark the run as failed on SIGTERM/SIGINT so Airflow sees a terminal state."""

    def _handler(signum: int, _frame: Any) -> None:  # noqa: ANN401
        signal_name = signal.Signals(signum).name
        _mark_failed(
            args=args,
            error_message=f"runner terminated by signal {signal_name} ({signum})",
            upsert_run=upsert_run,
        )
        # Re-raise to default handler so the process exits with the expected code
        signal.signal(signum, signal.SIG_DFL)
        raise SystemExit(128 + signum)

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, _handler)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    args = parse_args(argv)
    _install_signal_handlers(args, upsert_data_integrity_audit_run)
    return execute_run(args)


if __name__ == "__main__":
    sys.exit(main())
