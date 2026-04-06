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


sync_index_basic = _load_module("sync_index_basic", "scripts/daily/sync_index_basic.py")
sync_index_daily = _load_module("sync_index_daily", "scripts/daily/sync_index_daily.py")


def test_supported_markets_are_expected() -> None:
    assert sync_index_basic.SUPPORTED_MARKETS == ["SSE", "SZSE", "CSI", "CICC", "SW", "MSCI"]


def test_resolve_windows_splits_index_daily_dates() -> None:
    args = argparse.Namespace(
        start_date="20260301",
        end_date="20260310",
        last_days=0,
        sleep=0.0,
        index_codes="",
    )

    windows = sync_index_daily.resolve_windows(args, window_days=4)

    assert windows == [
        ("20260301", "20260304"),
        ("20260305", "20260308"),
        ("20260309", "20260310"),
    ]


def test_parse_index_codes_uses_default_whitelist_when_empty() -> None:
    assert sync_index_daily.parse_index_codes("") == sync_index_daily.DEFAULT_INDEX_DAILY_WHITELIST


def test_fetch_index_daily_page_uses_ts_code_window_and_offset(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_fetch_index_daily(**kwargs):  # noqa: ANN003
        captured.update(kwargs)
        return None

    monkeypatch.setattr(sync_index_daily, "fetch_index_daily", fake_fetch_index_daily)

    sync_index_daily.fetch_index_daily_page("000300.SH", "20260310", "20260313", 5000)

    assert captured == {
        "ts_code": "000300.SH",
        "start_date": "20260310",
        "end_date": "20260313",
        "offset": 5000,
        "limit": sync_index_daily._PAGE_SIZE,
    }
