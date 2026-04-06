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


sync_holdernumber = _load_module("sync_holdernumber", "scripts/daily/sync_holdernumber.py")
sync_top10_holders = _load_module("sync_top10_holders", "scripts/daily/sync_top10_holders.py")


def test_resolve_windows_splits_holdernumber_dates() -> None:
    args = argparse.Namespace(
        start_date="20260101",
        end_date="20260305",
        last_days=0,
        sleep=0.0,
    )

    windows = sync_holdernumber.resolve_windows(args, window_days=31)

    assert windows == [
        ("20260101", "20260131"),
        ("20260201", "20260303"),
        ("20260304", "20260305"),
    ]


def test_fetch_top10_page_uses_ann_date(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_fetch_top10_holders(**kwargs):  # noqa: ANN003
        captured.update(kwargs)
        return None

    monkeypatch.setattr(sync_top10_holders, "fetch_top10_holders", fake_fetch_top10_holders)

    sync_top10_holders.fetch_dataset_page("top10_holders", "20260315", 5000)

    assert captured["ann_date"] == "20260315"
    assert captured["offset"] == 5000


def test_resolve_top10_dates_prefers_holdernumber_ann_dates(monkeypatch) -> None:
    args = argparse.Namespace(
        dataset="top10_holders",
        start_date="20260101",
        end_date="20260131",
        last_days=0,
        sleep=0.0,
    )

    monkeypatch.setattr(
        sync_top10_holders,
        "load_ann_dates_from_holdernumber",
        lambda start_date, end_date: ["20260105", "20260120"],
    )

    dates = sync_top10_holders.resolve_dates(args)

    assert dates == ["20260105", "20260120"]
