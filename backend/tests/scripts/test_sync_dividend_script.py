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


sync_dividend = _load_module("sync_dividend", "scripts/daily/sync_dividend.py")


def test_resolve_dates_builds_daily_ann_date_list() -> None:
    args = argparse.Namespace(
        start_date="20260310",
        end_date="20260313",
        last_days=0,
        sleep=0.0,
    )

    dates = sync_dividend.resolve_dates(args)

    assert dates == ["20260310", "20260311", "20260312", "20260313"]


def test_resolve_dates_prefers_financial_ann_dates(monkeypatch) -> None:
    args = argparse.Namespace(
        start_date="20260310",
        end_date="20260313",
        last_days=0,
        sleep=0.0,
    )

    monkeypatch.setattr(
        sync_dividend,
        "load_ann_dates_from_financials",
        lambda start_date, end_date: ["20260311", "20260313"],
    )

    dates = sync_dividend.resolve_dates(args)

    assert dates == ["20260311", "20260313"]


def test_fetch_dividend_page_uses_ann_date_and_offset(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_fetch_dividend(**kwargs):  # noqa: ANN003
        captured.update(kwargs)
        return None

    monkeypatch.setattr(sync_dividend, "fetch_dividend", fake_fetch_dividend)

    sync_dividend.fetch_dividend_page("20260313", 5000)

    assert captured == {
        "ann_date": "20260313",
        "offset": 5000,
        "limit": sync_dividend._PAGE_SIZE,
    }
