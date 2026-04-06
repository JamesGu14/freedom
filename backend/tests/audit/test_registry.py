from __future__ import annotations

from app.audit.registry import (
    COVERAGE_GREEN_THRESHOLD,
    COVERAGE_YELLOW_THRESHOLD,
    EXCLUDED_FIRST_SCOPE_DATASETS,
    ROWCOUNT_RED_DROP_RATIO,
    ROWCOUNT_YELLOW_DROP_RATIO,
    get_dataset_registry,
)


def test_registry_contains_first_scope_datasets_with_expected_rules() -> None:
    registry = get_dataset_registry()

    assert "daily" in registry
    assert "daily_basic" in registry
    assert "daily_limit" in registry
    assert "indicators" in registry
    assert "adj_factor" in registry
    assert "cyq_perf" in registry
    assert "moneyflow_dc" in registry
    assert "shenwan_daily" in registry
    assert "citic_daily" in registry
    assert "market_index_dailybasic" in registry
    assert "index_factor_pro" in registry
    assert "moneyflow_hsgt" in registry

    assert registry["daily"].audit_mode == "date_only"
    assert registry["daily_basic"].audit_mode == "date_and_coverage"
    assert registry["daily_basic"].baseline_dataset == "daily"
    assert registry["daily_basic"].baseline_excluded_ts_code_suffixes == [".BJ"]
    assert registry["daily_basic"].baseline_excluded_ts_codes == ["600018.SH"]
    assert registry["daily_limit"].baseline_dataset == "daily"
    assert registry["daily_limit"].baseline_excluded_ts_code_suffixes == [".BJ"]
    assert registry["daily_limit"].baseline_excluded_ts_codes == ["001914.SZ"]
    assert registry["cyq_perf"].baseline_excluded_ts_code_suffixes == [".BJ"]
    assert registry["cyq_perf"].baseline_excluded_ts_codes == ["300114.SZ", "600898.SH"]
    assert registry["moneyflow_dc"].ignored_trade_dates == ["20231122"]
    assert registry["moneyflow_hsgt"].audit_mode == "date_only"
    assert registry["moneyflow_hsgt"].use_trade_calendar is False
    assert registry["market_index_dailybasic"].ignored_rowcount_trade_dates == ["20100531"]
    assert registry["index_factor_pro"].storage_type == "mongo"
    assert registry["index_factor_pro"].location == "index_factor_pro"
    assert registry["index_factor_pro"].rowcount_reference_storage_type == "parquet"
    assert registry["index_factor_pro"].rowcount_reference_location == "features/idx_factor_pro"


def test_registry_excludes_non_first_scope_datasets() -> None:
    registry = get_dataset_registry()

    assert "stk_surv" not in registry
    assert "stock_basic" not in registry
    assert "ccass_hold" not in registry
    assert "hk_hold" not in registry
    assert "cyq_chips" not in registry

    assert "stk_surv" in EXCLUDED_FIRST_SCOPE_DATASETS
    assert "cyq_chips" in EXCLUDED_FIRST_SCOPE_DATASETS


def test_registry_exposes_fixed_thresholds() -> None:
    assert COVERAGE_GREEN_THRESHOLD == 0.999
    assert COVERAGE_YELLOW_THRESHOLD == 0.99
    assert ROWCOUNT_YELLOW_DROP_RATIO == 0.20
    assert ROWCOUNT_RED_DROP_RATIO == 0.50
