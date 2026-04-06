from __future__ import annotations

import json
from pathlib import Path

from app.repair.p0_gap_repair import build_p0_targets
from scripts.repair.run_p0_gap_repair import parse_args, resolve_audit_summary_path, write_report


def test_parse_args_accepts_dataset_filter_and_run_id() -> None:
    args = parse_args(["--datasets", "moneyflow_dc,adj_factor", "--run-id", "repair-run"])

    assert args.datasets == "moneyflow_dc,adj_factor"
    assert args.run_id == "repair-run"


def test_resolve_audit_summary_path_uses_explicit_path(tmp_path: Path) -> None:
    summary_path = tmp_path / "summary.json"
    summary_path.write_text("{}", encoding="utf-8")

    assert resolve_audit_summary_path(str(summary_path)) == summary_path


def test_write_report_outputs_summary_and_json(tmp_path: Path) -> None:
    summary = {
        "datasets": [
            {
                "dataset": "moneyflow_dc",
                "date_gap": {"missing_trade_dates": ["20231122"]},
                "coverage_anomalies": [],
                "rowcount_anomalies": [],
            }
        ]
    }
    targets = build_p0_targets(summary)
    output_dir = tmp_path / "repair"
    report_path = write_report(
        output_dir=output_dir,
        targets=targets,
        results={
            "moneyflow_dc": [
                {"dataset": "moneyflow_dc", "trade_date": "20231122", "status": "success", "rows": 0}
            ]
        },
        compaction_recommendations={
            "moneyflow_dc": {"should_run": False, "reason": "compact_tool_unsupported"}
        },
    )

    assert report_path == output_dir / "summary.md"
    assert (output_dir / "summary.md").exists()
    summary_json = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary_json["datasets"]["moneyflow_dc"]["repair_dates"] == ["20231122"]
    assert summary_json["datasets"]["moneyflow_dc"]["compaction"]["reason"] == "compact_tool_unsupported"
