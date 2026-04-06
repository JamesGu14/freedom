from __future__ import annotations

from app.airflow_sync.trade_day_guard import normalize_trade_date, parse_trade_day_check_output


def test_normalize_trade_date_accepts_dash_and_compact_formats() -> None:
    assert normalize_trade_date("2026-03-15") == "20260315"
    assert normalize_trade_date("20260315") == "20260315"


def test_parse_trade_day_check_output_treats_one_as_true() -> None:
    assert parse_trade_day_check_output("1\n") is True
    assert parse_trade_day_check_output("0\n") is False

