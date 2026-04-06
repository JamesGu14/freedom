# P1 Index Data Design

## Scope

- `index_basic`
- `index_daily`

## Initial sync boundary

- `index_basic`: full dictionary sync
- `index_daily`: whitelist sync for 10 core indices only

## Index daily whitelist

- `000001.SH` 上证指数
- `399001.SZ` 深证成指
- `399006.SZ` 创业板指
- `000300.SH` 沪深300
- `000905.SH` 中证500
- `000852.SH` 中证1000
- `000016.SH` 上证50
- `399005.SZ` 中小100
- `000688.SH` 科创50
- `000015.SH` 红利指数

## Storage

- `index_basic` -> MongoDB collection `index_basic`
- `index_daily` -> MongoDB collection `index_daily`

## Why

- `index_basic` is a reference dictionary table, so MongoDB is enough and keeps the TuShare payload intact.
- `index_daily` is only 10 whitelisted series in the first phase, so MongoDB remains simple and consistent with the existing market-index data path.
- If the index universe expands substantially later, `index_daily` can be reconsidered for DuckDB or Parquet.

## Keys

- `index_basic`: unique key `ts_code`
- `index_daily`: unique key `ts_code + trade_date`

## Payload preservation

- Both collections preserve all TuShare-returned fields directly.

## Initial backfill strategy

- `index_basic`: pull the full dictionary across supported markets
- `index_daily`: backfill recent practical history for the 10-index whitelist

## Follow-up todo

- Future phase: expand `index_daily` from the 10-index whitelist to a broader 20-index or larger universe after validating sync cost and downstream usage.
