from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path


def _load_module(name: str, relative_path: str):
    module_path = Path(__file__).resolve().parents[2] / relative_path
    spec = importlib.util.spec_from_file_location(name, module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


generate_daily_stock_signals = _load_module(
    "generate_daily_stock_signals",
    "scripts/daily/generate_daily_stock_signals.py",
)


def test_normalize_date_accepts_yyyymmdd_and_yyyy_mm_dd() -> None:
    assert generate_daily_stock_signals.normalize_date("20260417") == "20260417"
    assert generate_daily_stock_signals.normalize_date("2026-04-17") == "20260417"


def test_resolve_dates_last_days_maps_natural_range_to_trading_days(monkeypatch) -> None:
    args = argparse.Namespace(
        trade_date=None,
        start_date=None,
        end_date="20260417",
        last_days=3,
    )

    monkeypatch.setattr(
        generate_daily_stock_signals,
        "get_open_trading_days",
        lambda start_date, end_date, exchange="SSE": ["20260415", "20260417"],
    )

    assert generate_daily_stock_signals.resolve_dates(args) == ["20260415", "20260417"]


def test_generate_for_date_writes_signal_and_resonance_docs(monkeypatch) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        generate_daily_stock_signals,
        "generate_daily_stock_signal_docs_for_range",
        lambda start_date, end_date, lookback_days=60: ([{"trade_date": start_date}], [{"trade_date": start_date}]),
    )
    monkeypatch.setattr(
        generate_daily_stock_signals,
        "upsert_daily_stock_signals",
        lambda docs: captured.__setitem__("signal_docs", docs) or len(docs),
    )
    monkeypatch.setattr(
        generate_daily_stock_signals,
        "upsert_daily_stock_signal_resonance",
        lambda docs: captured.__setitem__("resonance_docs", docs) or len(docs),
    )

    result = generate_daily_stock_signals.generate_for_date("20260417")

    assert result == {"trade_date": "20260417", "signal_docs": 1, "resonance_docs": 1}
    assert captured["signal_docs"] == [{"trade_date": "20260417"}]
    assert captured["resonance_docs"] == [{"trade_date": "20260417"}]
