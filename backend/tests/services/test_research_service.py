from __future__ import annotations

from app.services.research_service import (
    get_market_research_indexes,
    get_stock_research_holders,
    get_stock_research_overview,
)


def test_stock_research_overview_contains_expected_sections(monkeypatch) -> None:
    monkeypatch.setattr("app.services.research_service._get_stock_basic", lambda ts_code: {"ts_code": ts_code, "name": "平安银行"})
    monkeypatch.setattr("app.services.research_service._get_latest_daily", lambda ts_code: {"trade_date": "20260313", "close": 12.3})
    monkeypatch.setattr("app.services.research_service._get_latest_daily_basic", lambda ts_code: {"trade_date": "20260313", "pe": 8.8})
    monkeypatch.setattr("app.services.research_service._get_latest_indicator", lambda ts_code: {"trade_date": "20260313", "macd": 1.2})
    monkeypatch.setattr("app.services.research_service._get_latest_financial_indicator", lambda ts_code: {"end_date": "20251231", "roe": 12.5})
    monkeypatch.setattr("app.services.research_service._get_dividend_summary", lambda ts_code: {"latest_ann_date": "20260301"})
    monkeypatch.setattr("app.services.research_service._get_holder_summary", lambda ts_code: {"holder_num": 12345})
    monkeypatch.setattr("app.services.research_service._get_flow_summary", lambda ts_code: {"moneyflow_dc": 1000000})
    monkeypatch.setattr("app.services.research_service._get_event_summary", lambda ts_code: {"latest_suspend_date": "20260310"})

    payload = get_stock_research_overview("000001.SZ")

    assert payload["basic"]["name"] == "平安银行"
    assert payload["latest_daily_basic"]["pe"] == 8.8
    assert payload["latest_dividend_summary"]["latest_ann_date"] == "20260301"
    assert payload["latest_holder_summary"]["holder_num"] == 12345
    assert payload["latest_flow_summary"]["moneyflow_dc"] == 1000000
    assert payload["latest_event_summary"]["latest_suspend_date"] == "20260310"


def test_stock_research_holders_returns_summary_and_lists(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.research_service._get_holdernumber_rows",
        lambda ts_code, limit=24: [  # noqa: ARG005
            {"ann_date": "20260301", "end_date": "20251231", "holder_num": 10000},
            {"ann_date": "20251201", "end_date": "20250930", "holder_num": 11000},
        ],
    )
    monkeypatch.setattr(
        "app.services.research_service._get_top10_holder_rows",
        lambda collection_name, ts_code, limit=20: [  # noqa: ARG005
            {"end_date": "20251231", "hold_ratio": 12.0},
            {"end_date": "20251231", "hold_ratio": 8.0},
        ],
    )

    payload = get_stock_research_holders("000001.SZ")

    assert payload["summary"]["latest_holder_num"] == 10000
    assert payload["summary"]["holder_num_change"] == -1000
    assert payload["summary"]["top10_holder_ratio"] == 20.0
    assert payload["summary"]["top10_float_holder_ratio"] == 20.0
    assert len(payload["holder_number"]) == 2


def test_market_research_indexes_returns_snapshot(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.research_service._get_index_basic_map",
        lambda: {"000001.SH": {"ts_code": "000001.SH", "name": "上证指数", "market": "SSE"}},
    )
    monkeypatch.setattr(
        "app.services.research_service._get_index_daily_latest_rows",
        lambda codes: [{"ts_code": "000001.SH", "trade_date": "20260313", "close": 3200.0, "pct_chg": 0.5}],
    )
    monkeypatch.setattr("app.services.research_service._get_index_available_dates", lambda limit=60: ["20260313", "20260312"])  # noqa: ARG005

    payload = get_market_research_indexes()

    assert payload["tracked_indexes"][0]["ts_code"] == "000001.SH"
    assert payload["latest_snapshot"][0]["name"] == "上证指数"
    assert payload["available_dates"][0] == "20260313"
