from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from airflow import DAG
from airflow.exceptions import AirflowSkipException
from airflow.operators.python import PythonOperator
from airflow.utils.task_group import TaskGroup

FREEDOM_BACKEND_PATH = Path("/opt/freedom_backend")
if str(FREEDOM_BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(FREEDOM_BACKEND_PATH))

from app.airflow_sync.daily_sync_registry import DAILY_SYNC_TASKS  # noqa: E402
from app.airflow_sync.host_job_runner import HostJobRequest, run_host_job  # noqa: E402
from app.airflow_sync.trade_day_guard import is_trade_day  # noqa: E402


DAG_ID = "freedom_market_data_daily"
HOST_SSH_POOL = "freedom_host_ssh"
TZ = ZoneInfo("Asia/Shanghai")


def _trade_date_from_context(context: dict[str, object]) -> str:
    return str(context.get("ds_nodash") or "").strip()


def _precheck_trade_day(**context) -> None:
    trade_date = _trade_date_from_context(context)
    if not is_trade_day(trade_date):
        raise AirflowSkipException(f"{trade_date} is not an open SSE trading day")


def _run_task(task_id: str, **context) -> None:
    trade_date = _trade_date_from_context(context)
    task_spec = next(task for task in DAILY_SYNC_TASKS if task.task_id == task_id)
    run_id = str(context["run_id"])
    request = HostJobRequest(
        dag_id=DAG_ID,
        task_id=task_spec.task_id,
        run_id=run_id,
        trade_date=trade_date,
        command=task_spec.render_command(trade_date),
    )
    run_host_job(request)


def _finalize_run(**context) -> None:
    dag_run = context["dag_run"]
    counts = {"success": 0, "failed": 0, "skipped": 0}
    for task_instance in dag_run.get_task_instances():
        state = str(task_instance.state or "").lower()
        if state in counts:
            counts[state] += 1
    print({"dag_id": DAG_ID, "run_id": context["run_id"], "trade_date": _trade_date_from_context(context), "summary": counts})


with DAG(
    dag_id=DAG_ID,
    start_date=datetime(2026, 3, 1, tzinfo=TZ),
    schedule="30 20 * * 1-5",
    catchup=False,
    max_active_runs=1,
    max_active_tasks=3,
    tags=["freedom", "market-data", "daily-sync"],
) as dag:
    precheck_trade_day = PythonOperator(
        task_id="precheck_trade_day",
        python_callable=_precheck_trade_day,
    )

    groups: dict[str, TaskGroup] = {}
    group_tasks: dict[str, list[PythonOperator]] = {}
    for group_id in (
        "market_core",
        "factor_and_flow",
        "financials_and_corporate",
        "holders_and_margin",
        "index_and_industry",
        "signals_and_screeners",
    ):
        with TaskGroup(group_id=group_id) as task_group:
            created: list[PythonOperator] = []
            for task in [item for item in DAILY_SYNC_TASKS if item.group == group_id]:
                created.append(
                    PythonOperator(
                        task_id=task.task_id,
                        python_callable=_run_task,
                        op_kwargs={"task_id": task.task_id},
                        pool=HOST_SSH_POOL,
                        retries=task.retries,
                        retry_delay=timedelta(minutes=task.retry_delay_minutes),
                    )
                )
            groups[group_id] = task_group
            group_tasks[group_id] = created

    finalize_run = PythonOperator(
        task_id="finalize_run",
        python_callable=_finalize_run,
        trigger_rule="all_done",
    )

    precheck_trade_day >> groups["market_core"]
    precheck_trade_day >> groups["financials_and_corporate"]
    precheck_trade_day >> groups["holders_and_margin"]
    precheck_trade_day >> groups["index_and_industry"]
    groups["market_core"] >> groups["factor_and_flow"]
    groups["market_core"] >> groups["signals_and_screeners"]
    groups["factor_and_flow"] >> groups["signals_and_screeners"]

    groups["market_core"] >> finalize_run
    groups["factor_and_flow"] >> finalize_run
    groups["financials_and_corporate"] >> finalize_run
    groups["holders_and_margin"] >> finalize_run
    groups["index_and_industry"] >> finalize_run
    groups["signals_and_screeners"] >> finalize_run
