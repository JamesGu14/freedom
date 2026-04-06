from __future__ import annotations

from app.airflow_sync.daily_sync_registry import (
    DEFAULT_RETRIES,
    DEFAULT_RETRY_DELAY_MINUTES,
    DAILY_SYNC_TASKS,
    get_daily_sync_task,
)


def test_registry_contains_expected_groups_and_task_ids() -> None:
    task_ids = {task.task_id for task in DAILY_SYNC_TASKS}
    groups = {task.group for task in DAILY_SYNC_TASKS}

    assert "pull_daily_history" in task_ids
    assert "sync_dividend" in task_ids
    assert "sync_index_daily" in task_ids
    assert groups == {
        "market_core",
        "factor_and_flow",
        "financials_and_corporate",
        "holders_and_margin",
        "index_and_industry",
    }


def test_render_command_injects_trade_date_and_dataset_args() -> None:
    task = get_daily_sync_task("sync_dividend")

    command = task.render_command("20260315")

    assert command == [
        "python",
        "backend/scripts/daily/sync_dividend.py",
        "--start-date",
        "20260315",
        "--end-date",
        "20260315",
    ]


def test_registry_defaults_and_heavy_task_overrides() -> None:
    normal_task = get_daily_sync_task("sync_moneyflow_dc")
    heavy_task = get_daily_sync_task("sync_top10_holders")

    assert normal_task.retries == DEFAULT_RETRIES
    assert normal_task.retry_delay_minutes == DEFAULT_RETRY_DELAY_MINUTES
    assert heavy_task.retries == 3
    assert heavy_task.retry_delay_minutes == 15

