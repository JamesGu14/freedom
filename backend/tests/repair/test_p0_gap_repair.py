from __future__ import annotations

import duckdb
import pandas as pd

from app.repair.p0_gap_repair import (
    assess_compaction_need,
    build_p0_targets,
    extract_repair_dates,
    repair_adj_factor_dates,
    repair_trade_date,
    run_repairs,
)


def test_extract_repair_dates_merges_missing_and_anomalies() -> None:
    dataset_summary = {
        "dataset": "adj_factor",
        "date_gap": {
            "missing_trade_dates": ["20250205", "20250206", "20250205"],
        },
        "coverage_anomalies": [
            {"trade_date": "20250206"},
            {"trade_date": "20250207"},
        ],
        "rowcount_anomalies": [],
    }

    assert extract_repair_dates(dataset_summary) == ["20250205", "20250206", "20250207"]


def test_build_p0_targets_uses_audit_summary_only_for_supported_datasets() -> None:
    summary = {
        "datasets": [
            {
                "dataset": "moneyflow_dc",
                "date_gap": {"missing_trade_dates": ["20231122"]},
                "coverage_anomalies": [{"trade_date": "20231122"}],
                "rowcount_anomalies": [],
            },
            {
                "dataset": "adj_factor",
                "date_gap": {"missing_trade_dates": ["20250205", "20250206"]},
                "coverage_anomalies": [{"trade_date": "20250205"}],
                "rowcount_anomalies": [],
            },
            {
                "dataset": "index_factor_pro",
                "date_gap": {"missing_trade_dates": ["20060209"]},
                "coverage_anomalies": [],
                "rowcount_anomalies": [{"trade_date": "20250127"}],
            },
            {
                "dataset": "daily_basic",
                "date_gap": {"missing_trade_dates": []},
                "coverage_anomalies": [{"trade_date": "20210906"}],
                "rowcount_anomalies": [],
            },
        ]
    }

    targets = build_p0_targets(summary)

    assert list(targets.keys()) == ["moneyflow_dc", "adj_factor", "index_factor_pro"]
    assert targets["moneyflow_dc"].repair_dates == ["20231122"]
    assert targets["adj_factor"].repair_dates == ["20250205", "20250206"]
    assert targets["index_factor_pro"].repair_dates == ["20060209", "20250127"]


def test_repair_trade_date_routes_to_dataset_specific_handler(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    def fake_moneyflow_dc(trade_date: str) -> dict[str, object]:
        calls.append(("moneyflow_dc", trade_date))
        return {"dataset": "moneyflow_dc", "trade_date": trade_date, "status": "success", "rows": 1}

    def fake_adj_factor(trade_date: str) -> dict[str, object]:
        calls.append(("adj_factor", trade_date))
        return {"dataset": "adj_factor", "trade_date": trade_date, "status": "success", "rows": 2}

    def fake_index_factor(trade_date: str) -> dict[str, object]:
        calls.append(("index_factor_pro", trade_date))
        return {"dataset": "index_factor_pro", "trade_date": trade_date, "status": "success", "rows": 3}

    monkeypatch.setattr("app.repair.p0_gap_repair.repair_moneyflow_dc_date", fake_moneyflow_dc)
    monkeypatch.setattr("app.repair.p0_gap_repair.repair_adj_factor_date", fake_adj_factor)
    monkeypatch.setattr("app.repair.p0_gap_repair.repair_index_factor_pro_date", fake_index_factor)

    repair_trade_date("moneyflow_dc", "20231122")
    repair_trade_date("adj_factor", "20250205")
    repair_trade_date("index_factor_pro", "20060209")

    assert calls == [
        ("moneyflow_dc", "20231122"),
        ("adj_factor", "20250205"),
        ("index_factor_pro", "20060209"),
    ]


def test_assess_compaction_need_marks_p0_targets_as_no_action() -> None:
    targets = {
        "moneyflow_dc": build_p0_targets(
            {
                "datasets": [
                    {
                        "dataset": "moneyflow_dc",
                        "date_gap": {"missing_trade_dates": ["20231122"]},
                        "coverage_anomalies": [],
                        "rowcount_anomalies": [],
                    }
                ]
            }
        )["moneyflow_dc"],
        "adj_factor": build_p0_targets(
            {
                "datasets": [
                    {
                        "dataset": "adj_factor",
                        "date_gap": {"missing_trade_dates": ["20250205"]},
                        "coverage_anomalies": [],
                        "rowcount_anomalies": [],
                    }
                ]
            }
        )["adj_factor"],
        "index_factor_pro": build_p0_targets(
            {
                "datasets": [
                    {
                        "dataset": "index_factor_pro",
                        "date_gap": {"missing_trade_dates": ["20060209"]},
                        "coverage_anomalies": [],
                        "rowcount_anomalies": [],
                    }
                ]
            }
        )["index_factor_pro"],
    }

    recommendations = assess_compaction_need(targets)

    assert recommendations["moneyflow_dc"]["should_run"] is False
    assert recommendations["moneyflow_dc"]["reason"] == "compact_tool_unsupported"
    assert recommendations["adj_factor"]["should_run"] is False
    assert recommendations["adj_factor"]["reason"] == "not_parquet_dataset"
    assert recommendations["index_factor_pro"]["should_run"] is False
    assert recommendations["index_factor_pro"]["reason"] == "mongo_dataset"


def test_run_repairs_handles_adj_factor_batch_failure(monkeypatch) -> None:
    targets = build_p0_targets(
        {
            "datasets": [
                {
                    "dataset": "adj_factor",
                    "date_gap": {"missing_trade_dates": ["20250205", "20250206"]},
                    "coverage_anomalies": [],
                    "rowcount_anomalies": [],
                }
            ]
        }
    )

    monkeypatch.setattr(
        "app.repair.p0_gap_repair.repair_adj_factor_dates",
        lambda trade_dates: (_ for _ in ()).throw(RuntimeError("locked")),
    )

    results = run_repairs(targets)

    assert results["adj_factor"][0]["status"] == "error"
    assert results["adj_factor"][0]["trade_date"] == "20250205"
    assert "locked" in results["adj_factor"][0]["error"]
    assert results["adj_factor"][1]["trade_date"] == "20250206"


def test_repair_adj_factor_date_falls_back_to_file_swap_on_lock(monkeypatch) -> None:
    df = pd.DataFrame([{"ts_code": "000001.SZ", "trade_date": "20250205", "adj_factor": 1.0}])
    fallback_calls: list[str] = []

    monkeypatch.setattr("app.repair.p0_gap_repair.fetch_adj_factor", lambda trade_date: df)

    def raise_lock(_: pd.DataFrame) -> int:
        raise duckdb.IOException("Conflicting lock is held")

    monkeypatch.setattr("app.repair.p0_gap_repair.upsert_adj_factor", raise_lock)
    monkeypatch.setattr(
        "app.repair.p0_gap_repair._repair_adj_factor_via_file_swap",
        lambda raw_df, trade_date: fallback_calls.append(trade_date) or len(raw_df),
    )

    result = repair_trade_date("adj_factor", "20250205")

    assert fallback_calls == ["20250205"]
    assert result["status"] == "success"
    assert result["rows"] == 1


def test_run_repairs_batches_adj_factor_file_swap_once(monkeypatch) -> None:
    targets = build_p0_targets(
        {
            "datasets": [
                {
                    "dataset": "adj_factor",
                    "date_gap": {"missing_trade_dates": ["20250205", "20250206"]},
                    "coverage_anomalies": [],
                    "rowcount_anomalies": [],
                }
            ]
        }
    )
    batch_calls: list[list[str]] = []

    monkeypatch.setattr(
        "app.repair.p0_gap_repair.repair_adj_factor_dates",
        lambda trade_dates: batch_calls.append(trade_dates) or [
            {"dataset": "adj_factor", "trade_date": trade_date, "status": "success", "rows": 1}
            for trade_date in trade_dates
        ],
    )

    results = run_repairs(targets)

    assert batch_calls == [["20250205", "20250206"]]
    assert [row["trade_date"] for row in results["adj_factor"]] == ["20250205", "20250206"]


def test_repair_adj_factor_dates_falls_back_to_official_tushare(monkeypatch) -> None:
    df = pd.DataFrame([{"ts_code": "000001.SZ", "trade_date": "20250205", "adj_factor": 1.0}])
    calls: list[str] = []

    monkeypatch.setattr(
        "app.repair.p0_gap_repair.fetch_adj_factor",
        lambda trade_date: (_ for _ in ()).throw(ValueError("IP数量超限")),
    )
    monkeypatch.setattr(
        "app.repair.p0_gap_repair._fetch_adj_factor_via_tushare",
        lambda trade_date: calls.append(trade_date) or df,
    )
    monkeypatch.setattr(
        "app.repair.p0_gap_repair._repair_adj_factor_batch_via_file_swap",
        lambda frames: len(frames),
    )

    results = repair_adj_factor_dates(["20250205"])

    assert calls == ["20250205"]
    assert results[0]["status"] == "success"
