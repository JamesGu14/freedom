## ADDED Requirements

### Requirement: Fetch forecast data from TuShare
The system SHALL provide a `fetch_forecast` function in `tushare_client.py` that calls TuShare `forecast` API with parameters: `ts_code`, `ann_date`, `start_date`, `end_date`, `period`, `type`, `limit`, `offset`. `ts_code` is optional; the API supports querying by ann_date range alone.

#### Scenario: Fetch forecast by ann_date range
- **WHEN** `fetch_forecast(start_date='20250101', end_date='20250331')` is called without ts_code
- **THEN** the function SHALL return a DataFrame with columns including `ts_code`, `ann_date`, `end_date`, `type`, `p_change_min`, `p_change_max`, `net_profit_min`, `net_profit_max`, `last_parent_net`, `first_ann_date`, `summary`, `change_reason`

### Requirement: Fetch express data from TuShare
The system SHALL provide a `fetch_express` function in `tushare_client.py` that calls TuShare `express` API with parameters: `ts_code`, `ann_date`, `start_date`, `end_date`, `period`, `limit`, `offset`. `ts_code` is optional; the API supports querying by ann_date range alone.

#### Scenario: Fetch express by ann_date range
- **WHEN** `fetch_express(start_date='20250101', end_date='20250331')` is called without ts_code
- **THEN** the function SHALL return a DataFrame with columns including `ts_code`, `ann_date`, `end_date`, `revenue`, `operate_profit`, `total_profit`, `n_income`, `total_assets`, `total_hldr_eqy_exc_min_int`, `diluted_eps`, `diluted_roe`, `yoy_net_profit`, `bps`, `perf_summary`, `is_audit`

### Requirement: Store forecast in DuckDB
The system SHALL create a `forecast` table in DuckDB with key columns and `raw_payload`. Primary key SHALL be `(ts_code, ann_date, end_date)`.

#### Scenario: Upsert forecast records
- **WHEN** `upsert_forecast(df)` is called with a normalized DataFrame
- **THEN** the function SHALL insert new records and update existing records matched by `(ts_code, ann_date, end_date)`

### Requirement: Store express in DuckDB
The system SHALL create an `express` table in DuckDB with key columns and `raw_payload`. Primary key SHALL be `(ts_code, ann_date, end_date)`.

#### Scenario: Upsert express records
- **WHEN** `upsert_express(df)` is called with a normalized DataFrame
- **THEN** the function SHALL insert new records and update existing records matched by `(ts_code, ann_date, end_date)`

### Requirement: Sync forecast and express via sync_financial_reports.py
The system SHALL support `--dataset forecast` and `--dataset express` in `sync_financial_reports.py`, using the same window-based ann_date pagination and mark_sync_done pattern as existing datasets (income, balancesheet, etc.). These two APIs do NOT require ts_code and can query by ann_date range alone.

#### Scenario: Sync forecast for a date range
- **WHEN** `python sync_financial_reports.py --dataset forecast --start-date 20250101 --end-date 20250331` is run
- **THEN** the script SHALL fetch forecast data in 31-day ann_date windows, upsert into DuckDB, and call `mark_sync_done` for each window

#### Scenario: Sync express for a date range
- **WHEN** `python sync_financial_reports.py --dataset express --start-date 20250101 --end-date 20250331` is run
- **THEN** the script SHALL fetch express data in 31-day ann_date windows, upsert into DuckDB, and call `mark_sync_done` for each window
