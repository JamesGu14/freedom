from __future__ import annotations

import argparse
import datetime as dt
from dataclasses import replace
from collections import OrderedDict
from pathlib import Path

from app.audit.adapters import load_counts_by_date, load_open_trade_dates
from app.audit.engine import build_coverage_rows, classify_missing_dates, compute_date_gap, compute_rowcount_anomalies, worst_severity
from app.audit.models import AuditRunResult, DatasetAuditResult
from app.audit.models import DatasetConfig
from app.audit.registry import EXCLUDED_FIRST_SCOPE_DATASETS, get_dataset_registry
from app.audit.report_builder import write_audit_reports
from app.core.config import settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run local data integrity audit and write reports.")
    parser.add_argument("--datasets", type=str, default="", help="Comma-separated dataset names to audit")
    parser.add_argument("--run-id", type=str, default="", help="Fixed run id; defaults to timestamp")
    parser.add_argument("--start-date", type=str, default="", help="Optional lower date bound, YYYYMMDD or YYYY-MM-DD")
    parser.add_argument("--end-date", type=str, default="", help="Optional upper date bound, YYYYMMDD or YYYY-MM-DD")
    return parser


def _normalize_date(value: str | None) -> str | None:
    text = str(value or "").strip().replace("-", "")
    if not text:
        return None
    if len(text) != 8 or not text.isdigit():
        raise ValueError(f"invalid date: {value}")
    return text


def build_run_id(now: dt.datetime | None = None) -> str:
    current = now or dt.datetime.now()
    return current.strftime("%Y%m%d_%H%M%S")


def resolve_output_dir(run_id: str, log_dir: Path | None = None) -> Path:
    base_dir = log_dir or settings.log_dir
    return Path(base_dir) / "data_audit" / run_id


def select_datasets(registry: OrderedDict[str, object], names: list[str]) -> OrderedDict[str, object]:
    if not names:
        return registry
    selected = OrderedDict()
    for name in names:
        if name in registry:
            selected[name] = registry[name]
    return selected


def run_audit(
    *,
    selected_names: list[str] | None = None,
    run_id: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> AuditRunResult:
    registry = get_dataset_registry()
    selected = select_datasets(registry, selected_names or [])
    if not selected:
        raise ValueError("no datasets selected")

    normalized_start = _normalize_date(start_date)
    normalized_end = _normalize_date(end_date)
    calendar_dates = load_open_trade_dates(start_date=normalized_start, end_date=normalized_end)
    if not calendar_dates:
        raise ValueError("trade_calendar has no open dates in selected range")

    effective_run_id = run_id or build_run_id()
    output_dir = resolve_output_dir(effective_run_id)

    daily_counts: dict[str, int] | None = None
    if "daily" in selected:
        daily_counts = load_counts_by_date(
            registry["daily"],
            count_mode="distinct",
            start_date=normalized_start,
            end_date=normalized_end,
        )

    dataset_results: list[DatasetAuditResult] = []
    for config in selected.values():
        count_mode = "distinct" if config.audit_mode == "date_and_coverage" else "rows"
        if config.name == "daily" and daily_counts is not None:
            counts_by_date = daily_counts
        else:
            counts_by_date = load_counts_by_date(
                config,
                count_mode=count_mode,
                start_date=normalized_start,
                end_date=normalized_end,
            )
        actual_dates = sorted(counts_by_date)
        expected_calendar_dates = calendar_dates if config.use_trade_calendar else actual_dates
        date_gap = compute_date_gap(actual_dates, expected_calendar_dates, normalized_start, normalized_end)
        _apply_ignored_trade_dates(date_gap, config.ignored_trade_dates)
        coverage_anomalies = []
        rowcount_anomalies = []
        if config.audit_mode == "date_and_coverage":
            baseline_counts = daily_counts
            if config.baseline_dataset != "daily":
                raise ValueError(f"unsupported baseline dataset: {config.baseline_dataset}")
            if config.baseline_excluded_ts_code_suffixes or config.baseline_excluded_ts_codes:
                baseline_config = replace(
                    registry["daily"],
                    baseline_excluded_ts_code_suffixes=list(config.baseline_excluded_ts_code_suffixes),
                    baseline_excluded_ts_codes=list(config.baseline_excluded_ts_codes),
                )
                baseline_counts = load_counts_by_date(
                    baseline_config,
                    count_mode="distinct",
                    start_date=normalized_start,
                    end_date=normalized_end,
                )
            elif baseline_counts is None:
                baseline_counts = load_counts_by_date(
                    registry["daily"],
                    count_mode="distinct",
                    start_date=normalized_start,
                    end_date=normalized_end,
                )
            coverage_rows = build_coverage_rows(
                date_gap.expected_trade_dates,
                baseline_counts or {},
                counts_by_date,
                dataset=config.name,
            )
            coverage_anomalies = [
                item
                for item in coverage_rows
                if item.severity != "green" and item.trade_date not in set(config.ignored_trade_dates)
            ]
        elif config.audit_mode == "date_and_rowcount":
            reference_counts_by_date: dict[str, int] | None = None
            if config.rowcount_reference_storage_type and config.rowcount_reference_location and config.rowcount_reference_date_field:
                reference_config = DatasetConfig(
                    name=f"{config.name}_rowcount_reference",
                    storage_type=config.rowcount_reference_storage_type,
                    location=config.rowcount_reference_location,
                    date_field=config.rowcount_reference_date_field,
                    audit_mode="date_only",
                )
                reference_counts_by_date = load_counts_by_date(
                    reference_config,
                    count_mode="rows",
                    start_date=normalized_start,
                    end_date=normalized_end,
                )
            rowcount_anomalies = compute_rowcount_anomalies(
                counts_by_date,
                dataset=config.name,
                reference_counts_by_date=reference_counts_by_date,
            )
            if config.ignored_rowcount_trade_dates:
                ignored = set(config.ignored_rowcount_trade_dates)
                rowcount_anomalies = [item for item in rowcount_anomalies if item.trade_date not in ignored]

        status = worst_severity(
            [date_gap.severity]
            + [item.severity for item in coverage_anomalies]
            + [item.severity for item in rowcount_anomalies]
        )
        dataset_results.append(
            DatasetAuditResult(
                dataset=config.name,
                audit_mode=config.audit_mode,
                local_min_date=date_gap.local_min_date,
                local_max_date=date_gap.local_max_date,
                status=status,
                date_gap=date_gap,
                coverage_anomalies=coverage_anomalies,
                rowcount_anomalies=rowcount_anomalies,
            )
        )

    result = AuditRunResult(
        run_id=effective_run_id,
        output_dir=str(output_dir),
        datasets=dataset_results,
        excluded_datasets=list(EXCLUDED_FIRST_SCOPE_DATASETS),
    )
    write_audit_reports(output_dir, result)
    return result


def _apply_ignored_trade_dates(date_gap, ignored_trade_dates: list[str]) -> None:
    if not ignored_trade_dates:
        return
    ignored = {item for item in ignored_trade_dates}
    filtered_expected = [item for item in date_gap.expected_trade_dates if item not in ignored]
    filtered_missing = [item for item in date_gap.missing_trade_dates if item not in ignored]
    date_gap.expected_trade_dates = filtered_expected
    date_gap.expected_trade_date_count = len(filtered_expected)
    date_gap.missing_trade_dates = filtered_missing
    date_gap.actual_trade_date_count = len(filtered_expected) - len(filtered_missing)
    date_gap.missing_ranges = [[item, item] for item in filtered_missing]
    date_gap.severity = classify_missing_dates(filtered_missing)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    names = [item.strip() for item in str(args.datasets or "").split(",") if item.strip()]
    result = run_audit(
        selected_names=names,
        run_id=(args.run_id or None),
        start_date=(args.start_date or None),
        end_date=(args.end_date or None),
    )
    print(f"run_id={result.run_id}")
    print(f"output_dir={result.output_dir}")
    for item in result.datasets:
        print(
            f"{item.dataset}: status={item.status} "
            f"missing_dates={len(item.date_gap.missing_trade_dates)} "
            f"coverage_anomalies={len(item.coverage_anomalies)} "
            f"rowcount_anomalies={len(item.rowcount_anomalies)}"
        )


if __name__ == "__main__":
    main()
