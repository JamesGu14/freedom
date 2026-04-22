from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types


def _install_airflow_stubs() -> None:
    current = {"dag": None, "group": None}

    airflow_module = types.ModuleType("airflow")
    exceptions_module = types.ModuleType("airflow.exceptions")
    operators_module = types.ModuleType("airflow.operators")
    python_module = types.ModuleType("airflow.operators.python")
    utils_module = types.ModuleType("airflow.utils")
    task_group_module = types.ModuleType("airflow.utils.task_group")

    class AirflowSkipException(Exception):
        pass

    class DAG:
        def __init__(self, *, dag_id: str, schedule: str, **kwargs):  # noqa: ANN003
            self.dag_id = dag_id
            self.schedule = schedule
            self.start_date = kwargs.get("start_date")
            self.max_active_tasks = kwargs.get("max_active_tasks")
            self.tasks = []

        def __enter__(self):
            current["dag"] = self
            return self

        def __exit__(self, exc_type, exc, tb):  # noqa: ANN001, ANN201
            current["dag"] = None
            return False

    class TaskGroup:
        def __init__(self, *, group_id: str):
            self.group_id = group_id

        def __enter__(self):
            current["group"] = self.group_id
            return self

        def __exit__(self, exc_type, exc, tb):  # noqa: ANN001, ANN201
            current["group"] = None
            return False

        def __rshift__(self, other):  # noqa: ANN001, ANN201
            return other

    class PythonOperator:
        def __init__(self, *, task_id: str, **kwargs):  # noqa: ANN003
            group = current["group"]
            self.task_id = f"{group}.{task_id}" if group else task_id
            self.pool = kwargs.get("pool")
            dag = current["dag"]
            if dag is not None:
                dag.tasks.append(self)

        def __rshift__(self, other):  # noqa: ANN001, ANN201
            return other

    airflow_module.DAG = DAG
    exceptions_module.AirflowSkipException = AirflowSkipException
    python_module.PythonOperator = PythonOperator
    task_group_module.TaskGroup = TaskGroup

    sys.modules["airflow"] = airflow_module
    sys.modules["airflow.exceptions"] = exceptions_module
    sys.modules["airflow.operators"] = operators_module
    sys.modules["airflow.operators.python"] = python_module
    sys.modules["airflow.utils"] = utils_module
    sys.modules["airflow.utils.task_group"] = task_group_module


def _load_module(name: str, relative_path: str):
    _install_airflow_stubs()
    module_path = Path(__file__).resolve().parents[2] / relative_path
    spec = importlib.util.spec_from_file_location(name, module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_daily_market_data_dag_has_expected_schedule_and_groups() -> None:
    module = _load_module("freedom_market_data_daily", "airflow/dags/freedom_market_data_daily.py")
    dag = module.dag

    assert dag.dag_id == "freedom_market_data_daily"
    assert str(dag.schedule) == "30 20 * * 1-5"
    assert str(dag.start_date.date()) <= "2026-03-02"
    assert dag.max_active_tasks == 3

    task_ids = {task.task_id for task in dag.tasks}
    assert "precheck_trade_day" in task_ids
    assert "finalize_run" in task_ids
    assert "market_core.pull_daily_history" in task_ids
    assert "financials_and_corporate.sync_dividend" in task_ids
    assert "signals_and_screeners.generate_daily_stock_signals" in task_ids
    pull_daily = next(task for task in dag.tasks if task.task_id == "market_core.pull_daily_history")
    assert pull_daily.pool == "freedom_host_ssh"
