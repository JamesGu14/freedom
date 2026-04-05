from __future__ import annotations

import datetime as dt
import statistics

from app.audit.models import CoverageAnomaly, DateGapResult, RowCountAnomaly
from app.audit.registry import (
    COVERAGE_GREEN_THRESHOLD,
    COVERAGE_YELLOW_THRESHOLD,
    ROWCOUNT_RED_DROP_RATIO,
    ROWCOUNT_YELLOW_DROP_RATIO,
)


def _normalize_date(value: str) -> str:
    return str(value or "").replace("-", "").strip()


def _to_date(value: str) -> dt.date:
    return dt.datetime.strptime(value, "%Y%m%d").date()


def _build_missing_ranges(dates: list[str]) -> list[list[str]]:
    if not dates:
        return []
    ordered = sorted(dates)
    ranges: list[list[str]] = [[ordered[0], ordered[0]]]
    for current in ordered[1:]:
        previous = ranges[-1][1]
        if (_to_date(current) - _to_date(previous)).days == 1:
            ranges[-1][1] = current
        else:
            ranges.append([current, current])
    return ranges


def classify_missing_dates(missing_dates: list[str]) -> str:
    if not missing_dates:
        return "green"
    ranges = _build_missing_ranges(missing_dates)
    if len(missing_dates) >= 5 or any(start != end for start, end in ranges):
        return "red"
    return "yellow"


def compute_date_gap(
    actual_dates: list[str],
    open_calendar_dates: list[str],
    start_date: str | None = None,
    end_date: str | None = None,
) -> DateGapResult:
    normalized_actual = sorted({_normalize_date(item) for item in actual_dates if _normalize_date(item)})
    normalized_calendar = sorted({_normalize_date(item) for item in open_calendar_dates if _normalize_date(item)})

    if start_date:
        normalized_actual = [item for item in normalized_actual if item >= _normalize_date(start_date)]
        normalized_calendar = [item for item in normalized_calendar if item >= _normalize_date(start_date)]
    if end_date:
        normalized_actual = [item for item in normalized_actual if item <= _normalize_date(end_date)]
        normalized_calendar = [item for item in normalized_calendar if item <= _normalize_date(end_date)]

    if not normalized_actual:
        return DateGapResult(
            local_min_date=None,
            local_max_date=None,
            expected_trade_date_count=0,
            actual_trade_date_count=0,
            missing_trade_dates=[],
            severity="red",
            expected_trade_dates=[],
            missing_ranges=[],
        )

    local_min = normalized_actual[0]
    local_max = normalized_actual[-1]
    expected = [item for item in normalized_calendar if local_min <= item <= local_max]
    missing = sorted(set(expected).difference(normalized_actual))
    return DateGapResult(
        local_min_date=local_min,
        local_max_date=local_max,
        expected_trade_date_count=len(expected),
        actual_trade_date_count=len(normalized_actual),
        missing_trade_dates=missing,
        severity=classify_missing_dates(missing),
        expected_trade_dates=expected,
        missing_ranges=_build_missing_ranges(missing),
    )


def classify_coverage_ratio(ratio: float) -> str:
    if ratio >= COVERAGE_GREEN_THRESHOLD:
        return "green"
    if ratio >= COVERAGE_YELLOW_THRESHOLD:
        return "yellow"
    return "red"


def build_coverage_rows(
    expected_dates: list[str],
    baseline_counts: dict[str, int],
    dataset_counts: dict[str, int],
    dataset: str = "",
) -> list[CoverageAnomaly]:
    rows: list[CoverageAnomaly] = []
    for trade_date in expected_dates:
        baseline_count = int(baseline_counts.get(trade_date, 0) or 0)
        if baseline_count <= 0:
            continue
        dataset_count = int(dataset_counts.get(trade_date, 0) or 0)
        missing_count = max(baseline_count - dataset_count, 0)
        ratio = 1.0 if baseline_count == 0 else dataset_count / baseline_count
        rows.append(
            CoverageAnomaly(
                dataset=dataset,
                trade_date=trade_date,
                baseline_count=baseline_count,
                dataset_count=dataset_count,
                missing_count=missing_count,
                coverage_ratio=ratio,
                severity=classify_coverage_ratio(ratio),
            )
        )
    return rows


def compute_rowcount_anomalies(
    counts_by_date: dict[str, int],
    dataset: str = "",
    lookback: int = 20,
    reference_counts_by_date: dict[str, int] | None = None,
) -> list[RowCountAnomaly]:
    anomalies: list[RowCountAnomaly] = []
    ordered_dates = sorted(counts_by_date)
    history: list[int] = []
    for index, trade_date in enumerate(ordered_dates):
        row_count = int(counts_by_date.get(trade_date, 0) or 0)
        if len(history) < lookback:
            history.append(row_count)
            continue
        median_lookback = float(statistics.median(history[-lookback:]))
        reference_count = int((reference_counts_by_date or {}).get(trade_date, 0) or 0)
        baseline_count = median_lookback
        baseline_source = "median_20d"
        if reference_count > 0:
            baseline_count = float(reference_count)
            baseline_source = "reference"
        deviation_ratio = 0.0
        if baseline_count > 0:
            deviation_ratio = round(max(0.0, 1.0 - (row_count / baseline_count)), 6)
        severity = ""
        if deviation_ratio > ROWCOUNT_RED_DROP_RATIO:
            severity = "red"
        elif deviation_ratio > ROWCOUNT_YELLOW_DROP_RATIO:
            severity = "yellow"
        if severity:
            if _is_persistent_rowcount_regime_shift(ordered_dates, counts_by_date, index, row_count):
                history.append(row_count)
                continue
            anomalies.append(
                RowCountAnomaly(
                    dataset=dataset,
                    trade_date=trade_date,
                    row_count=row_count,
                    median_lookback=median_lookback,
                    baseline_count=baseline_count,
                    baseline_source=baseline_source,
                    deviation_ratio=deviation_ratio,
                    severity=severity,
                )
            )
        history.append(row_count)
    return anomalies


def _is_persistent_rowcount_regime_shift(
    ordered_dates: list[str],
    counts_by_date: dict[str, int],
    index: int,
    row_count: int,
    lookahead: int = 5,
) -> bool:
    future_dates = ordered_dates[index + 1 : index + 1 + lookahead]
    if len(future_dates) < lookahead:
        return False
    future_counts = [int(counts_by_date.get(item, 0) or 0) for item in future_dates]
    return all(item == row_count for item in future_counts)


def worst_severity(values: list[str]) -> str:
    if "red" in values:
        return "red"
    if "yellow" in values:
        return "yellow"
    return "green"
