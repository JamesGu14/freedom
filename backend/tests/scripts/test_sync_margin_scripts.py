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


sync_margin = _load_module("sync_margin", "scripts/daily/sync_margin.py")
sync_margin_detail = _load_module("sync_margin_detail", "scripts/daily/sync_margin_detail.py")


def test_resolve_windows_splits_margin_dates() -> None:
    args = argparse.Namespace(
        start_date="20260301",
        end_date="20260310",
        last_days=0,
        sleep=0.0,
    )

    windows = sync_margin.resolve_windows(args, window_days=4)

    assert windows == [
        ("20260301", "20260304"),
        ("20260305", "20260308"),
        ("20260309", "20260310"),
    ]


def test_fetch_margin_page_uses_start_end_and_offset(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_fetch_margin(**kwargs):  # noqa: ANN003
        captured.update(kwargs)
        return None

    monkeypatch.setattr(sync_margin, "fetch_margin", fake_fetch_margin)

    sync_margin.fetch_margin_page("20260310", "20260313", 5000)

    assert captured == {
        "start_date": "20260310",
        "end_date": "20260313",
        "offset": 5000,
        "limit": sync_margin._PAGE_SIZE,
    }


def test_fetch_margin_detail_page_uses_start_end_and_offset(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_fetch_margin_detail(**kwargs):  # noqa: ANN003
        captured.update(kwargs)
        return None

    monkeypatch.setattr(sync_margin_detail, "fetch_margin_detail", fake_fetch_margin_detail)

    sync_margin_detail.fetch_margin_detail_page("20260310", "20260313", 3000)

    assert captured == {
        "start_date": "20260310",
        "end_date": "20260313",
        "offset": 3000,
        "limit": sync_margin_detail._PAGE_SIZE,
    }
