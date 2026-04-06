from __future__ import annotations

from app.audit.engine import (
    build_coverage_rows,
    classify_coverage_ratio,
    compute_date_gap,
    compute_rowcount_anomalies,
)


def test_compute_date_gap_uses_local_range_and_finds_missing_trade_dates() -> None:
    result = compute_date_gap(
        actual_dates=["20260303", "20260305"],
        open_calendar_dates=["20260303", "20260304", "20260305", "20260306"],
    )

    assert result.local_min_date == "20260303"
    assert result.local_max_date == "20260305"
    assert result.expected_trade_date_count == 3
    assert result.actual_trade_date_count == 2
    assert result.missing_trade_dates == ["20260304"]
    assert result.severity == "yellow"


def test_classify_coverage_ratio_uses_agreed_thresholds() -> None:
    assert classify_coverage_ratio(1.0) == "green"
    assert classify_coverage_ratio(0.999) == "green"
    assert classify_coverage_ratio(0.995) == "yellow"
    assert classify_coverage_ratio(0.98) == "red"


def test_build_coverage_rows_compares_against_daily_baseline() -> None:
    rows = build_coverage_rows(
        expected_dates=["20260303", "20260304"],
        baseline_counts={"20260303": 1000, "20260304": 1000},
        dataset_counts={"20260303": 995, "20260304": 980},
    )

    assert [row.trade_date for row in rows] == ["20260303", "20260304"]
    assert rows[0].coverage_ratio == 0.995
    assert rows[0].severity == "yellow"
    assert rows[1].coverage_ratio == 0.98
    assert rows[1].severity == "red"
    assert rows[1].missing_count == 20


def test_compute_rowcount_anomalies_flags_large_drops_against_recent_median() -> None:
    stable_counts = {f"202602{day:02d}": 100 for day in range(1, 21)}
    stable_counts["20260221"] = 70
    stable_counts["20260222"] = 40

    anomalies = compute_rowcount_anomalies(stable_counts, lookback=20)

    assert [row.trade_date for row in anomalies] == ["20260221", "20260222"]
    assert anomalies[0].median_lookback == 100
    assert anomalies[0].deviation_ratio == 0.30
    assert anomalies[0].severity == "yellow"
    assert anomalies[1].deviation_ratio == 0.60
    assert anomalies[1].severity == "red"


def test_compute_rowcount_anomalies_prefers_same_day_reference_counts() -> None:
    stable_counts = {f"202506{day:02d}": 879 for day in range(1, 21)}
    stable_counts["20250621"] = 587
    stable_counts["20250622"] = 341

    anomalies = compute_rowcount_anomalies(
        stable_counts,
        lookback=20,
        reference_counts_by_date={
            "20250621": 587,
            "20250622": 587,
        },
    )

    assert [row.trade_date for row in anomalies] == ["20250622"]
    assert anomalies[0].baseline_count == 587
    assert anomalies[0].baseline_source == "reference"
    assert anomalies[0].median_lookback == 879


def test_compute_rowcount_anomalies_suppresses_persistent_regime_shifts() -> None:
    counts = {f"202112{day:02d}": 587 for day in range(1, 11)}
    for day in range(13, 29):
        counts[f"202112{day:02d}"] = 439

    anomalies = compute_rowcount_anomalies(counts, lookback=10)

    assert anomalies == []
