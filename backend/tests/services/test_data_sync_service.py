from __future__ import annotations

from app.services.data_sync_service import get_calendar_status, get_missing_dates


def test_get_calendar_status_returns_task_level_details(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.data_sync_service._build_trade_calendar_range",
        lambda start, end: [  # noqa: ARG005
            {"cal_date": "20260313", "is_open": 1},
            {"cal_date": "20260314", "is_open": 1},
            {"cal_date": "20260315", "is_open": 0},
        ],
    )
    monkeypatch.setattr(
        "app.services.data_sync_service._build_sync_task_map",
        lambda start, end: {  # noqa: ARG005
            "20260313": {
                "pull_daily",
                "sync_suspend_d",
                "sync_stk_factor_pro",
                "sync_cyq_perf",
                "sync_moneyflow_dc",
                "sync_moneyflow_hsgt",
                "sync_income",
                "sync_balancesheet",
                "sync_cashflow",
                "sync_fina_indicator",
                "sync_dividend",
                "sync_stk_holdernumber",
                "sync_top10_holders",
                "sync_top10_floatholders",
                "sync_margin",
                "sync_margin_detail",
                "sync_index_daily",
                "sync_shenwan_daily",
                "sync_zhishu_data",
            },
            "20260314": {
                "pull_daily",
                "sync_suspend_d",
                "sync_stk_factor_pro",
            },
        },
    )

    payload = get_calendar_status("20260313", "20260315")

    assert payload["summary"] == {
        "trading_days": 2,
        "synced_all_required": 1,
        "partially_synced": 1,
        "missing": 0,
        "non_trading": 1,
    }
    assert payload["required_tasks"][0]["task"] == "pull_daily"
    assert payload["required_tasks"][0]["label"] == "日线主链路"

    first = payload["items"][0]
    assert first["status"] == "synced_all_required"
    assert first["missing_required_tasks"] == []
    assert all(item["status"] == "synced" for item in first["task_statuses"])

    second = payload["items"][1]
    assert second["status"] == "partially_synced"
    assert "sync_dividend" in second["missing_required_tasks"]
    assert "分红送股" in second["missing_required_task_labels"]
    assert any(item["task"] == "sync_dividend" and item["status"] == "missing" for item in second["task_statuses"])

    third = payload["items"][2]
    assert third["status"] == "non_trading"
    assert third["task_statuses"] == []


def test_get_missing_dates_returns_labels_for_partial_or_missing_days(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.data_sync_service.get_calendar_status",
        lambda start, end: {  # noqa: ARG005
            "start_date": "20260313",
            "end_date": "20260315",
            "required_tasks": [{"task": "pull_daily", "label": "日线主链路"}],
            "items": [
                {
                    "trade_date": "20260313",
                    "is_open": True,
                    "status": "synced_all_required",
                    "missing_required_tasks": [],
                    "missing_required_task_labels": [],
                    "completed_required_tasks": ["pull_daily"],
                    "completed_required_task_labels": ["日线主链路"],
                    "task_statuses": [{"task": "pull_daily", "label": "日线主链路", "status": "synced"}],
                },
                {
                    "trade_date": "20260314",
                    "is_open": True,
                    "status": "missing",
                    "missing_required_tasks": ["pull_daily"],
                    "missing_required_task_labels": ["日线主链路"],
                    "completed_required_tasks": [],
                    "completed_required_task_labels": [],
                    "task_statuses": [{"task": "pull_daily", "label": "日线主链路", "status": "missing"}],
                },
            ],
        },
    )

    payload = get_missing_dates("20260313", "20260315")

    assert payload["total_missing_dates"] == 1
    assert payload["items"][0]["trade_date"] == "20260314"
    assert payload["items"][0]["missing_required_task_labels"] == ["日线主链路"]

