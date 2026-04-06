# Spec Delta: data-integrity-audit

## ADDED Requirements

### Requirement: Audit Local Daily Datasets
WHEN an operator runs the local data integrity audit,
the system SHALL scan each configured daily-frequency dataset using only local MongoDB, DuckDB, and Parquet data.

#### Scenario: Audit configured datasets
GIVEN the audit registry defines a set of supported daily-frequency datasets
WHEN the operator starts an audit run
THEN the system scans each configured dataset
AND the system does not call any remote data source for validation

#### Scenario: Skip unsupported datasets
GIVEN a dataset is marked as excluded from the first audit scope
WHEN the operator starts an audit run
THEN the system excludes that dataset from the run
AND the system records that exclusion in the audit output

### Requirement: Detect Missing Trade Dates
WHEN the system audits a daily-frequency dataset,
the system SHALL compare the dataset's local date coverage against the trading calendar within that dataset's local date range.

#### Scenario: Find missing trade dates
GIVEN a dataset has a local minimum date and local maximum date
AND the trading calendar contains open dates within that range
WHEN the system compares the dataset dates to the trading calendar
THEN the system identifies missing trade dates within that range
AND the system records the missing trade dates in the audit results

#### Scenario: Respect local dataset start date
GIVEN a dataset begins later than the platform's earliest trading calendar date
WHEN the system performs the date gap audit
THEN the system starts auditing from the dataset's local minimum date
AND the system does not report dates before that local minimum date as missing

### Requirement: Compare Stock Coverage Against Daily Baseline
WHEN the system audits a stock-level daily matrix dataset other than `daily`,
the system SHALL compare that dataset's per-trade-date stock coverage against the `daily` dataset for the same trade date.

#### Scenario: Measure per-date coverage ratio
GIVEN `daily` contains a set of `ts_code` values for a trade date
AND another stock-level dataset contains its own set of `ts_code` values for the same trade date
WHEN the system performs coverage comparison
THEN the system calculates the baseline stock count
AND the system calculates the dataset stock count
AND the system calculates the missing stock count and coverage ratio

#### Scenario: Avoid stock_basic-based false positives
GIVEN `stock_basic` contains stocks that are not part of the effective local daily research universe for a trade date
WHEN the system performs coverage comparison
THEN the system uses `daily` as the baseline dataset
AND the system does not use `stock_basic` as the stock coverage baseline

### Requirement: Detect Row Count Anomalies For Market Datasets
WHEN the system audits a market-level or index-level daily dataset,
the system SHALL detect suspicious per-date row count drops.

#### Scenario: Flag abnormal row count drop
GIVEN a market-level dataset has historical per-date row counts
AND the system can derive a rolling reference from recent valid dates
WHEN a trade date's row count falls materially below the recent reference
THEN the system marks that trade date as a row count anomaly
AND the system records the anomaly in the audit results

#### Scenario: Keep stable datasets green
GIVEN a market-level dataset has no missing trade dates
AND its row counts stay within the configured tolerance
WHEN the system completes the audit
THEN the system marks that dataset as healthy

#### Scenario: Exclude moneyflow_hsgt from row count anomaly audit
GIVEN `moneyflow_hsgt` is configured as a date-only dataset
WHEN the system runs the market dataset audit
THEN the system checks `moneyflow_hsgt` only for missing trade dates
AND the system does not apply row count anomaly detection to `moneyflow_hsgt`

### Requirement: Audit Mongo index_factor_pro In The First Scope
WHEN the system audits index factor data in the first implementation scope,
the system SHALL use Mongo `index_factor_pro` as the authoritative audit target.

#### Scenario: Use Mongo index_factor_pro
GIVEN the repository contains both Parquet `features/idx_factor_pro` and Mongo `index_factor_pro`
WHEN the system performs the first-scope index factor audit
THEN the system audits Mongo `index_factor_pro`
AND the system does not audit Parquet `features/idx_factor_pro` in that scope

#### Scenario: Keep index factor audit aligned with current online usage
GIVEN current online workflows read from Mongo `index_factor_pro`
WHEN the system defines the first-scope audit target
THEN the system aligns the audit target with Mongo `index_factor_pro`
AND the resulting report reflects the active business data path

### Requirement: Produce Multi-Format Audit Reports
WHEN an audit run completes,
the system SHALL write human-readable and machine-readable outputs to a report directory.

#### Scenario: Write report artifacts
GIVEN an audit run has finished
WHEN the system writes outputs
THEN the system produces a Markdown summary report
AND the system produces CSV detail files for missing dates and anomalies
AND the system produces a JSON summary artifact

#### Scenario: Summarize dataset status
GIVEN the audit run has findings across multiple datasets
WHEN the system builds the summary report
THEN the report shows each dataset's local date range
AND the report shows each dataset's status severity
AND the report highlights critical findings

#### Scenario: Write reports to the fixed audit directory
GIVEN an audit run has a generated run identifier
WHEN the system writes report artifacts
THEN the system writes them under `logs/data_audit/<run_id>/`
AND the system keeps one run's artifacts separate from another run's artifacts
