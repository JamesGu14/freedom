from __future__ import annotations

import csv
import json
from pathlib import Path

from app.audit.models import AuditRunResult


def _write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return path


def _build_summary_markdown(result: AuditRunResult) -> str:
    datasets = result.datasets
    green = sum(1 for item in datasets if item.status == "green")
    yellow = sum(1 for item in datasets if item.status == "yellow")
    red = sum(1 for item in datasets if item.status == "red")
    lines = [
        "# Data Integrity Audit Report",
        "",
        f"- run_id: {result.run_id}",
        f"- datasets: {len(datasets)}",
        f"- green: {green}",
        f"- yellow: {yellow}",
        f"- red: {red}",
    ]
    if result.excluded_datasets:
        lines.extend(["", "## Excluded", ""])
        for name in result.excluded_datasets:
            lines.append(f"- {name}")

    lines.extend(["", "## Datasets", ""])
    for item in datasets:
        lines.append(
            f"- {item.dataset}: status={item.status}, "
            f"range={item.local_min_date or '-'}~{item.local_max_date or '-'}, "
            f"missing_dates={len(item.date_gap.missing_trade_dates)}, "
            f"coverage_anomalies={len(item.coverage_anomalies)}, "
            f"rowcount_anomalies={len(item.rowcount_anomalies)}"
        )
    return "\n".join(lines) + "\n"


def write_audit_reports(output_dir: Path, result: AuditRunResult) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    summary_md = output_dir / "summary.md"
    summary_md.write_text(_build_summary_markdown(result), encoding="utf-8")
    written.append(summary_md)

    missing_rows: list[dict] = []
    coverage_rows: list[dict] = []
    rowcount_rows: list[dict] = []
    for dataset in result.datasets:
        for trade_date in dataset.date_gap.missing_trade_dates:
            missing_rows.append(
                {
                    "dataset": dataset.dataset,
                    "trade_date": trade_date,
                    "issue_type": "missing_trade_date",
                    "severity": dataset.date_gap.severity,
                }
            )
        for row in dataset.coverage_anomalies:
            coverage_rows.append(
                {
                    "dataset": row.dataset,
                    "trade_date": row.trade_date,
                    "daily_count": row.baseline_count,
                    "dataset_count": row.dataset_count,
                    "missing_count": row.missing_count,
                    "coverage_ratio": f"{row.coverage_ratio:.6f}",
                    "severity": row.severity,
                }
            )
        for row in dataset.rowcount_anomalies:
            rowcount_rows.append(
                {
                    "dataset": row.dataset,
                    "trade_date": row.trade_date,
                    "row_count": row.row_count,
                    "median_20d": f"{row.median_lookback:.6f}",
                    "baseline_count": f"{row.baseline_count:.6f}",
                    "baseline_source": row.baseline_source,
                    "deviation_ratio": f"{row.deviation_ratio:.6f}",
                    "severity": row.severity,
                }
            )

    written.append(
        _write_csv(
            output_dir / "missing_dates.csv",
            missing_rows,
            ["dataset", "trade_date", "issue_type", "severity"],
        )
    )
    written.append(
        _write_csv(
            output_dir / "coverage_anomalies.csv",
            coverage_rows,
            ["dataset", "trade_date", "daily_count", "dataset_count", "missing_count", "coverage_ratio", "severity"],
        )
    )
    written.append(
        _write_csv(
            output_dir / "rowcount_anomalies.csv",
            rowcount_rows,
            ["dataset", "trade_date", "row_count", "median_20d", "baseline_count", "baseline_source", "deviation_ratio", "severity"],
        )
    )

    summary_json = output_dir / "summary.json"
    summary_json.write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    written.append(summary_json)
    return written
