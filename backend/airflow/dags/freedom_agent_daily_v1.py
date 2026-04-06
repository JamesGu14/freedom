from __future__ import annotations

import json
import os
from datetime import datetime
from urllib import error, parse, request

import pendulum
from airflow import DAG
from airflow.exceptions import AirflowException
from airflow.operators.python import PythonOperator

DAG_ID = "freedom_agent_daily_v1"
BACKEND_API_BASE = os.getenv("FREEDOM_BACKEND_API_BASE", "http://backend:9000/api").rstrip("/")
FREEDOM_API_KEY = os.getenv("FREEDOM_API_KEY", "").strip()


def _post_json(url: str, payload: dict[str, object], token: str | None = None) -> dict[str, object]:
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = request.Request(url=url, data=body, headers=headers, method="POST")
    with request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get_json(url: str, token: str | None = None) -> dict[str, object]:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = request.Request(url=url, headers=headers, method="GET")
    with request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _automation_access_token() -> str:
    if not FREEDOM_API_KEY:
        raise AirflowException("FREEDOM_API_KEY is required")
    return FREEDOM_API_KEY


def _noop_step(step_name: str, **context) -> None:  # noqa: ARG001
    print(f"[{DAG_ID}] step={step_name} ts={datetime.utcnow().isoformat()}")


def _trigger_agent_run(**context) -> None:
    trade_date = str(context.get("ds_nodash") or "").strip()
    token = _automation_access_token()
    query = parse.urlencode({"trade_date": trade_date})
    result = _post_json(f"{BACKEND_API_BASE}/agent-freedom/run?{query}", payload={}, token=token)
    status = str(result.get("status") or "").strip()
    if status not in {"success", "degraded", "skipped"}:
        raise AirflowException(f"agent run failed: {result}")


def _verify_report(**context) -> None:
    trade_date = str(context.get("ds_nodash") or "").strip()
    token = _automation_access_token()
    query = parse.urlencode({"trade_date": trade_date})
    data = _get_json(f"{BACKEND_API_BASE}/agent-freedom/report/latest?{query}", token=token)
    item = data.get("item") if isinstance(data, dict) else None
    if not isinstance(item, dict):
        raise AirflowException("report/latest returned empty item")


def _verify_push(**context) -> None:
    trade_date = str(context.get("ds_nodash") or "").strip()
    token = _automation_access_token()
    query = parse.urlencode({"trade_date": trade_date})
    data = _get_json(f"{BACKEND_API_BASE}/agent-freedom/report/latest?{query}", token=token)
    item = data.get("item") if isinstance(data, dict) else None
    if not isinstance(item, dict):
        raise AirflowException("report/latest returned empty item")
    push = item.get("push") if isinstance(item.get("push"), dict) else {}
    push_status = str(push.get("status") or "")
    if push_status == "failed":
        raise AirflowException(f"feishu push failed: {push}")


with DAG(
    dag_id=DAG_ID,
    start_date=datetime(2026, 2, 28, tzinfo=pendulum.timezone("Asia/Shanghai")),
    schedule="0 20 * * *",
    catchup=False,
    max_active_runs=1,
    tags=["freedom", "agent"],
) as dag:
    t1_precheck_trade_day = PythonOperator(
        task_id="t1_precheck_trade_day",
        python_callable=_noop_step,
        op_kwargs={"step_name": "t1_precheck_trade_day"},
    )
    t2_data_quality_check = PythonOperator(
        task_id="t2_data_quality_check",
        python_callable=_noop_step,
        op_kwargs={"step_name": "t2_data_quality_check"},
    )
    t3_call_skill_findata = PythonOperator(
        task_id="t3_call_skill_findata",
        python_callable=_noop_step,
        op_kwargs={"step_name": "t3_call_skill_findata"},
    )
    t4_call_skill_quant_factor = PythonOperator(
        task_id="t4_call_skill_quant_factor",
        python_callable=_noop_step,
        op_kwargs={"step_name": "t4_call_skill_quant_factor"},
    )
    t5_call_skill_sector_rotation = PythonOperator(
        task_id="t5_call_skill_sector_rotation",
        python_callable=_noop_step,
        op_kwargs={"step_name": "t5_call_skill_sector_rotation"},
    )
    t6_market_regime_engine = PythonOperator(
        task_id="t6_market_regime_engine",
        python_callable=_noop_step,
        op_kwargs={"step_name": "t6_market_regime_engine"},
    )
    t7_industry_rotation_engine = PythonOperator(
        task_id="t7_industry_rotation_engine",
        python_callable=_noop_step,
        op_kwargs={"step_name": "t7_industry_rotation_engine"},
    )
    t8_stock_scoring_v1 = PythonOperator(
        task_id="t8_stock_scoring_v1",
        python_callable=_noop_step,
        op_kwargs={"step_name": "t8_stock_scoring_v1"},
    )
    t9_risk_control_v1 = PythonOperator(
        task_id="t9_risk_control_v1",
        python_callable=_noop_step,
        op_kwargs={"step_name": "t9_risk_control_v1"},
    )
    t10_persist_strategy_signals = PythonOperator(
        task_id="t10_persist_strategy_signals",
        python_callable=_trigger_agent_run,
    )
    t11_generate_report_markdown_and_api_payload = PythonOperator(
        task_id="t11_generate_report_markdown_and_api_payload",
        python_callable=_verify_report,
    )
    t12_push_feishu_daily = PythonOperator(
        task_id="t12_push_feishu_daily",
        python_callable=_verify_push,
    )
    t13_finalize_run_record = PythonOperator(
        task_id="t13_finalize_run_record",
        python_callable=_noop_step,
        op_kwargs={"step_name": "t13_finalize_run_record"},
    )

    (
        t1_precheck_trade_day
        >> t2_data_quality_check
        >> t3_call_skill_findata
        >> t4_call_skill_quant_factor
        >> t5_call_skill_sector_rotation
        >> t6_market_regime_engine
        >> t7_industry_rotation_engine
        >> t8_stock_scoring_v1
        >> t9_risk_control_v1
        >> t10_persist_strategy_signals
        >> t11_generate_report_markdown_and_api_payload
        >> t12_push_feishu_daily
        >> t13_finalize_run_record
    )
