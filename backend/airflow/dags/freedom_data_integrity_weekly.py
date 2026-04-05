from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pendulum
from airflow import DAG
from airflow.operators.python import PythonOperator

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.append(str(BACKEND_ROOT))

from app.audit.airflow_runner import run_weekly_airflow_audit


DAG_ID = "freedom_data_integrity_weekly"
TZ = pendulum.timezone("Asia/Shanghai")


def _run_weekly_data_integrity_audit(**context) -> dict[str, object]:
    logical_date = context.get("logical_date")
    scheduled_for = logical_date.isoformat() if logical_date else datetime.now(tz=TZ).isoformat()
    return run_weekly_airflow_audit(
        dag_id=DAG_ID,
        task_id="run_weekly_data_integrity_audit",
        scheduled_for=scheduled_for,
    )


with DAG(
    dag_id=DAG_ID,
    start_date=datetime(2026, 3, 14, tzinfo=TZ),
    schedule="0 6 * * 6",
    catchup=False,
    max_active_runs=1,
    tags=["freedom", "audit", "data-integrity"],
) as dag:
    run_weekly_data_integrity_audit = PythonOperator(
        task_id="run_weekly_data_integrity_audit",
        python_callable=_run_weekly_data_integrity_audit,
    )
