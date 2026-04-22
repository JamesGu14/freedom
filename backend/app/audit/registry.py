from __future__ import annotations

from collections import OrderedDict

from app.audit.models import DatasetConfig

COVERAGE_GREEN_THRESHOLD = 0.999
COVERAGE_YELLOW_THRESHOLD = 0.99
ROWCOUNT_YELLOW_DROP_RATIO = 0.20
ROWCOUNT_RED_DROP_RATIO = 0.50

EXCLUDED_FIRST_SCOPE_DATASETS = (
    "stk_surv",
    "stock_basic",
    "shenwan_industry_member",
    "citic_industry_member",
    "ccass_hold",
    "hk_hold",
    "cyq_chips",
)


def get_dataset_registry() -> OrderedDict[str, DatasetConfig]:
    items = [
        DatasetConfig(
            name="daily",
            storage_type="parquet",
            location="raw/daily",
            date_field="trade_date",
            audit_mode="date_only",
            coverage_key="ts_code",
        ),
        DatasetConfig(
            name="daily_basic",
            storage_type="parquet",
            location="raw/daily_basic",
            date_field="trade_date",
            audit_mode="date_and_coverage",
            coverage_key="ts_code",
            baseline_dataset="daily",
            baseline_excluded_ts_code_suffixes=[".BJ"],
            baseline_excluded_ts_codes=["600018.SH"],
        ),
        DatasetConfig(
            name="daily_limit",
            storage_type="parquet",
            location="raw/daily_limit",
            date_field="trade_date",
            audit_mode="date_and_coverage",
            coverage_key="ts_code",
            baseline_dataset="daily",
            baseline_excluded_ts_code_suffixes=[".BJ"],
            baseline_excluded_ts_codes=["001914.SZ"],
        ),
        DatasetConfig(
            name="indicators",
            storage_type="parquet",
            location="features/indicators",
            date_field="trade_date",
            audit_mode="date_and_coverage",
            coverage_key="ts_code",
            baseline_dataset="daily",
        ),
        DatasetConfig(
            name="adj_factor",
            storage_type="parquet",
            location="raw/adj_factor",
            date_field="trade_date",
            audit_mode="date_and_coverage",
            coverage_key="ts_code",
            baseline_dataset="daily",
        ),
        DatasetConfig(
            name="cyq_perf",
            storage_type="parquet",
            location="features/cyq_perf",
            date_field="trade_date",
            audit_mode="date_and_coverage",
            coverage_key="ts_code",
            baseline_dataset="daily",
            baseline_excluded_ts_code_suffixes=[".BJ"],
            baseline_excluded_ts_codes=["300114.SZ", "600898.SH"],
        ),
        DatasetConfig(
            name="moneyflow_dc",
            storage_type="parquet",
            location="features/moneyflow_dc",
            date_field="trade_date",
            audit_mode="date_and_coverage",
            coverage_key="ts_code",
            baseline_dataset="daily",
            ignored_trade_dates=["20231122"],
        ),
        DatasetConfig(
            name="shenwan_daily",
            storage_type="mongo",
            location="shenwan_daily",
            date_field="trade_date",
            audit_mode="date_and_rowcount",
        ),
        DatasetConfig(
            name="citic_daily",
            storage_type="mongo",
            location="citic_daily",
            date_field="trade_date",
            audit_mode="date_and_rowcount",
        ),
        DatasetConfig(
            name="market_index_dailybasic",
            storage_type="mongo",
            location="market_index_dailybasic",
            date_field="trade_date",
            audit_mode="date_and_rowcount",
            ignored_rowcount_trade_dates=["20100531"],
        ),
        DatasetConfig(
            name="index_factor_pro",
            storage_type="mongo",
            location="index_factor_pro",
            date_field="trade_date",
            audit_mode="date_and_rowcount",
            rowcount_reference_storage_type="parquet",
            rowcount_reference_location="features/idx_factor_pro",
            rowcount_reference_date_field="trade_date",
        ),
        DatasetConfig(
            name="moneyflow_hsgt",
            storage_type="mongo",
            location="moneyflow_hsgt",
            date_field="trade_date",
            audit_mode="date_only",
            use_trade_calendar=False,
        ),
    ]
    return OrderedDict((item.name, item) for item in items)
