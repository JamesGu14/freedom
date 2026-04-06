## ADDED Requirements

### Requirement: Fetch fina_audit data from TuShare
The system SHALL provide a `fetch_fina_audit` function in `tushare_client.py` that calls TuShare `fina_audit` API with parameters: `ts_code` (required), `ann_date`, `start_date`, `end_date`, `period`, `limit`, `offset`. The `ts_code` parameter is mandatory per the TuShare API.

#### Scenario: Fetch audit opinions for a stock by ann_date range
- **WHEN** `fetch_fina_audit(ts_code='600000.SH', start_date='20250101', end_date='20250331')` is called
- **THEN** the function SHALL return a DataFrame with columns: `ts_code`, `ann_date`, `end_date`, `audit_result`, `audit_fees`, `audit_agency`, `audit_sign`

### Requirement: Fetch fina_mainbz data from TuShare
The system SHALL provide a `fetch_fina_mainbz` function in `tushare_client.py` that calls TuShare `fina_mainbz` API with parameters: `ts_code` (required), `period`, `type`, `start_date`, `end_date`, `limit`, `offset`. Note: `start_date`/`end_date` in this API mean **reporting period range** (not announcement date range), per TuShare documentation. The API returns max 100 rows per request.

#### Scenario: Fetch main business composition by ts_code and period
- **WHEN** `fetch_fina_mainbz(ts_code='000001.SZ', period='20241231', type='P')` is called
- **THEN** the function SHALL return a DataFrame with columns: `ts_code`, `end_date`, `bz_item`, `bz_sales`, `bz_profit`, `bz_cost`, `curr_type`, `update_flag`

#### Scenario: Fetch main business by ts_code and period range
- **WHEN** `fetch_fina_mainbz(ts_code='000001.SZ', start_date='20240101', end_date='20241231')` is called
- **THEN** the function SHALL return all business composition data for that stock across reporting periods 20240331, 20240630, 20240930, 20241231

### Requirement: Store fina_audit in DuckDB
The system SHALL create a `fina_audit` table in DuckDB with key columns: `ts_code`, `ann_date`, `end_date`, `audit_result`, `audit_fees`, `audit_agency`, `audit_sign`, `raw_payload`. Primary key SHALL be `(ts_code, ann_date, end_date)`.

#### Scenario: Upsert fina_audit records
- **WHEN** `upsert_fina_audit(df)` is called with a normalized DataFrame
- **THEN** the function SHALL insert new records and update existing records matched by `(ts_code, ann_date, end_date)`

### Requirement: Store fina_mainbz in DuckDB
The system SHALL create a `fina_mainbz` table in DuckDB with key columns: `ts_code`, `end_date`, `bz_item`, `bz_sales`, `bz_profit`, `bz_cost`, `curr_type`, `update_flag`, `raw_payload`. Primary key SHALL be `(ts_code, end_date, bz_item, curr_type)`.

#### Scenario: Upsert fina_mainbz records
- **WHEN** `upsert_fina_mainbz(df)` is called with a normalized DataFrame
- **THEN** the function SHALL insert new records and update existing records matched by `(ts_code, end_date, bz_item, curr_type)`

### Requirement: Sync fina_audit via dedicated script
The system SHALL provide a new `sync_fina_audit.py` script that iterates over all stocks from `stock_basic` and fetches audit opinions per stock. The `ts_code` parameter is mandatory in the TuShare API, so window-based ann_date-only queries are not possible. The script SHALL support `--start-date`/`--end-date` (ann_date range), `--last-days`, `--ts-codes` (comma-separated for testing), `--sleep` (default 1.0).

#### Scenario: Sync fina_audit with last-days
- **WHEN** `python sync_fina_audit.py --last-days 30` is run
- **THEN** the script SHALL iterate all stocks from stock_basic, call `fetch_fina_audit(ts_code=code, start_date=start, end_date=end)` for each, upsert into DuckDB, and call `mark_sync_done(end_date, 'sync_fina_audit')` after all stocks are processed

#### Scenario: Test with specific stocks
- **WHEN** `python sync_fina_audit.py --ts-codes 000001.SZ,600000.SH --last-days 365` is run
- **THEN** the script SHALL only iterate the specified stocks

#### Scenario: Empty result for a stock
- **WHEN** a stock has no audit opinions in the date range
- **THEN** the script SHALL log a debug message and continue to the next stock

### Requirement: Sync fina_mainbz via dedicated script
The system SHALL provide a new `sync_fina_mainbz.py` script that iterates over all stocks and fetches main business composition data. The script SHALL support `--period` (single reporting period like 20241231), `--period-start`/`--period-end` (reporting period range, to avoid confusion with ann_date), `--ts-codes` (comma-separated for testing), `--sleep` (default 1.5).

#### Scenario: Single period sync
- **WHEN** `python sync_fina_mainbz.py --period 20241231` is run
- **THEN** the script SHALL iterate all stocks, fetch data for the specified period, handle pagination (if `len(df) == 100` then fetch next page with offset), upsert into DuckDB, and call `mark_sync_done('20241231', 'sync_fina_mainbz')` only after all stocks are processed

#### Scenario: Period range sync
- **WHEN** `python sync_fina_mainbz.py --period-start 20240101 --period-end 20241231` is run
- **THEN** the script SHALL iterate all stocks, fetch data with `start_date`/`end_date` as period range, upsert into DuckDB

#### Scenario: Graceful handling of empty/delisted stocks
- **WHEN** a stock returns empty data
- **THEN** the script SHALL log a debug message and continue to the next stock

#### Scenario: Partial failure does not mark sync done
- **WHEN** the script fails midway through the stock list
- **THEN** `mark_sync_done` SHALL NOT be called, allowing a clean re-run next time (upsert ensures idempotency)
