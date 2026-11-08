from __future__ import annotations

import os
from types import SimpleNamespace

import pandas as pd
import pytest

from scripts.daily.compact_parquet import DEDUP_KEYS, compact_partition


@pytest.mark.parametrize("dataset", ["moneyflow_dc", "cyq_perf", "fina_audit", "forecast", "express"])
def test_compaction_keeps_newest_record_when_uuid_names_sort_backwards(tmp_path, dataset) -> None:
    partition = tmp_path / "ts_code=000001.SZ" / "year=2026"
    partition.mkdir(parents=True)
    row = {key: "1" if key == "type" else "20261030" for key in DEDUP_KEYS[dataset]}
    row["ts_code"] = "000001.SZ"
    older = partition / "part-ffffffff.parquet"
    newer = partition / "part-00000001.parquet"
    pd.DataFrame([{**row, "value": 1.0}]).to_parquet(older, index=False)
    pd.DataFrame([{**row, "value": 2.0}]).to_parquet(newer, index=False)
    os.utime(older, ns=(1_000_000_000, 1_000_000_000))
    os.utime(newer, ns=(2_000_000_000, 2_000_000_000))

    compact_partition(partition, DEDUP_KEYS[dataset])

    result = pd.read_parquet(partition / "part-0000.parquet")
    assert result["value"].tolist() == [2.0]
    assert not older.exists()
    assert not newer.exists()


def test_compaction_does_not_make_old_rows_newer_than_concurrent_writes(monkeypatch, tmp_path) -> None:
    from scripts.daily import compact_parquet

    row = {"ts_code": "000001.SZ", "trade_date": "20261030"}
    for suffix, value in [("old", 1), ("new", 2)]:
        part = tmp_path / f"part-{suffix}.parquet"
        pd.DataFrame([{**row, "value": value}]).to_parquet(part, index=False)
        os.utime(part, ns=(value * 1_000_000_000, value * 1_000_000_000))

    calls = 0

    def create_temp_id():
        nonlocal calls
        calls += 1
        if calls == 1:
            # This file arrives after the compactor snapshots its input paths.
            part = tmp_path / "part-concurrent.parquet"
            pd.DataFrame([{**row, "value": 3}]).to_parquet(part, index=False)
            os.utime(part, ns=(3_000_000_000, 3_000_000_000))
        return SimpleNamespace(hex=f"test-{calls}")

    monkeypatch.setattr(compact_parquet, "uuid", SimpleNamespace(uuid4=create_temp_id))
    compact_partition(tmp_path)
    assert (tmp_path / "part-concurrent.parquet").exists()
    compact_partition(tmp_path)

    assert pd.read_parquet(tmp_path / "part-0000.parquet")["value"].tolist() == [3]
