from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

import pandas as pd

MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "daily" / "sync_financial_reports.py"
SPEC = importlib.util.spec_from_file_location("sync_financial_reports", MODULE_PATH)
assert SPEC and SPEC.loader
sync_financial_reports = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sync_financial_reports)


def test_resolve_windows_splits_date_range_into_chunks() -> None:
    args = argparse.Namespace(
        dataset="income",
        start_date="20260101",
        end_date="20260305",
        last_days=0,
        sleep=0.0,
    )

    windows = sync_financial_reports.resolve_windows(args, window_days=31)

    assert windows == [
        ("20260101", "20260131"),
        ("20260201", "20260303"),
        ("20260304", "20260305"),
    ]


def test_fetch_dataset_page_uses_date_window(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_fetch_income(**kwargs):  # noqa: ANN003
        captured.update(kwargs)
        return None

    monkeypatch.setattr(sync_financial_reports, "fetch_income", fake_fetch_income)

    sync_financial_reports.fetch_dataset_page("income", "20260101", "20260131", 5000)

    assert captured["start_date"] == "20260101"
    assert captured["end_date"] == "20260131"
    assert captured["offset"] == 5000
    assert "ann_date" not in captured


def test_normalize_date_columns_preserves_missing_values() -> None:
    frame = pd.DataFrame(
        [
            {"ann_date": "2026-03-15", "f_ann_date": None, "end_date": "2025-12-31"},
            {"ann_date": None, "f_ann_date": "", "end_date": None},
        ]
    )

    normalized = sync_financial_reports.normalize_date_columns(frame)

    assert normalized.loc[0, "ann_date"] == "20260315"
    assert normalized.loc[0, "end_date"] == "20251231"
    assert normalized.loc[0, "f_ann_date"] is None
    assert normalized.loc[1, "ann_date"] is None
    assert normalized.loc[1, "end_date"] is None
