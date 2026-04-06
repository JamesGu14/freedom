## ADDED Requirements

### Requirement: Fetch disclosure_date data from TuShare
The system SHALL provide a `fetch_disclosure_date` function in `tushare_client.py` that calls TuShare `disclosure_date` API with parameters: `ts_code`, `end_date` (reporting period), `pre_date`, `actual_date`, `limit`, `offset`. Note: `end_date` here means **reporting period** (e.g. 20241231 = 2024 annual report), NOT announcement date range. Max 3000 rows per request.

#### Scenario: Fetch disclosure dates by reporting period
- **WHEN** `fetch_disclosure_date(end_date='20241231')` is called
- **THEN** the function SHALL return a DataFrame with all stocks' disclosure schedule for that period, with columns: `ts_code`, `ann_date`, `end_date`, `pre_date`, `actual_date`, `modify_date`

#### Scenario: Fetch disclosure date for a specific stock
- **WHEN** `fetch_disclosure_date(ts_code='000001.SZ', end_date='20241231')` is called
- **THEN** the function SHALL return that stock's disclosure schedule for the period

### Requirement: Store disclosure_date in DuckDB
The system SHALL create a `disclosure_date` table in DuckDB with key columns: `ts_code`, `end_date`, `ann_date`, `pre_date`, `actual_date`, `modify_date`, `raw_payload`. Primary key SHALL be `(ts_code, end_date)`.

#### Scenario: Upsert disclosure_date records
- **WHEN** `upsert_disclosure_date(df)` is called with a normalized DataFrame
- **THEN** the function SHALL insert new records and update existing records matched by `(ts_code, end_date)`

### Requirement: Sync disclosure_date via dedicated script
The system SHALL provide a new `sync_disclosure_date.py` script that queries by reporting period. The script SHALL support `--year` (syncs all 4 standard periods: 0331/0630/0930/1231), `--period` (single period), `--recent N` (most recent N reporting periods based on current date), `--sleep` (default 0.5). Pagination: offset-based, max 3000/request, continue while `len(df) == limit`.

#### Scenario: Sync disclosure dates for a year
- **WHEN** `python sync_disclosure_date.py --year 2024` is run
- **THEN** the script SHALL fetch disclosure dates for periods 20240331, 20240630, 20240930, 20241231, with offset pagination, upsert into DuckDB, and call `mark_sync_done(period, 'sync_disclosure_date')` per period

#### Scenario: Sync disclosure dates for recent periods
- **WHEN** `python sync_disclosure_date.py --recent 2` is run (current date is 2025-06-15)
- **THEN** the script SHALL determine the 2 most recent reporting periods (20250331, 20250630), fetch and upsert their disclosure dates

#### Scenario: Pagination handling
- **WHEN** a reporting period has more than 3000 stocks
- **THEN** the script SHALL request with offset=0, offset=3000, etc. until `len(df) < 3000`

### Requirement: Daily scheduling in daily.sh
The system SHALL add Steps 13-16 in `daily.sh` (TOTAL_STEPS from 12 to 16) for financial report data sync, each as an independent `run_step_task` call:

- Step 13: `sync_financial_reports.py --dataset forecast --last-days 7`
- Step 14: `sync_financial_reports.py --dataset express --last-days 7`
- Step 15: `sync_fina_audit.py --last-days 30`
- Step 16: `sync_disclosure_date.py --recent 2`

fina_mainbz is NOT included in daily.sh (run manually per quarter). A comment after Step 16 SHALL document this.

#### Scenario: daily.sh runs financial report sync steps
- **WHEN** daily.sh executes Steps 13-16
- **THEN** each step SHALL run via `run_step_task` with standard logging

#### Scenario: Single step failure
- **WHEN** Step 13 (forecast) fails due to API timeout
- **THEN** daily.sh SHALL exit per `set -euo pipefail` (consistent with Steps 1-12 behavior)
