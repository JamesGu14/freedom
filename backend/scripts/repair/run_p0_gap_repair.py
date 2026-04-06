from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
from pathlib import Path
import sys

SCRIPT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(SCRIPT_ROOT))

from app.repair.p0_gap_repair import (
    RepairTarget,
    assess_compaction_need,
    build_p0_targets,
    load_audit_summary,
    run_repairs,
)

logger = logging.getLogger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Repair P0 data gaps using an audit summary.")
    parser.add_argument("--audit-summary", type=str, default="", help="Path to audit summary.json")
    parser.add_argument("--datasets", type=str, default="", help="Comma-separated dataset names")
    parser.add_argument("--run-id", type=str, default="", help="Fixed run id")
    parser.add_argument("--log-dir", type=str, default="logs", help="Base log directory")
    return parser.parse_args(argv)


def resolve_audit_summary_path(path_value: str) -> Path:
    if path_value:
        return Path(path_value).expanduser().resolve()

    root = Path("logs/data_audit")
    candidates = sorted(root.glob("*/summary.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    if not candidates:
        raise ValueError("audit summary path is required")
    return candidates[0].resolve()


def resolve_output_dir(*, run_id: str, log_dir: Path) -> Path:
    return log_dir / "data_repair" / run_id


def write_report(
    *,
    output_dir: Path,
    targets: dict[str, RepairTarget],
    results: dict[str, list[dict[str, object]]],
    compaction_recommendations: dict[str, dict[str, object]],
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)

    summary_payload = {"datasets": {}}
    lines = ["# P0 Gap Repair Report", ""]
    for dataset_name, target in targets.items():
        summary_payload["datasets"][dataset_name] = {
            "repair_dates": target.repair_dates,
            "results": results.get(dataset_name, []),
            "compaction": compaction_recommendations.get(dataset_name, {}),
        }
        lines.append(f"## {dataset_name}")
        lines.append(f"- repair_dates: {len(target.repair_dates)}")
        lines.append(f"- compaction: {compaction_recommendations.get(dataset_name, {}).get('reason', 'unknown')}")
        lines.append("")

    summary_md = output_dir / "summary.md"
    summary_md.write_text("\n".join(lines), encoding="utf-8")
    (output_dir / "summary.json").write_text(json.dumps(summary_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary_md


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    args = parse_args(argv)
    audit_summary_path = resolve_audit_summary_path(args.audit_summary)
    summary = load_audit_summary(audit_summary_path)
    selected = [item.strip() for item in args.datasets.split(",") if item.strip()]
    targets = build_p0_targets(summary, selected_datasets=selected or None)
    if not targets:
        raise SystemExit("No P0 repair targets selected")

    run_id = args.run_id.strip() or dt.datetime.now().strftime("p0_repair_%Y%m%d_%H%M%S")
    output_dir = resolve_output_dir(run_id=run_id, log_dir=Path(args.log_dir))
    results = run_repairs(targets)
    compaction = assess_compaction_need(targets)
    report_path = write_report(
        output_dir=output_dir,
        targets=targets,
        results=results,
        compaction_recommendations=compaction,
    )
    logger.info("repair report written to %s", report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
