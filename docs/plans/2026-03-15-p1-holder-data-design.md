# P1 Holder Data Design

**Scope**
- `stk_holdernumber`
- `top10_holders`
- `top10_floatholders`

**Decision**
- `stk_holdernumber` -> DuckDB table `stk_holdernumber`
- `top10_holders` -> Mongo collection `top10_holders`
- `top10_floatholders` -> Mongo collection `top10_floatholders`

**Why**
- `stk_holdernumber` is a compact time-series table keyed by `ts_code + end_date`, which fits DuckDB well for later screening and joins.
- `top10_holders` and `top10_floatholders` are report-detail records keyed by `ts_code + end_date + holder_name`, which are easier to preserve in Mongo without premature schema expansion.
- All three data sources must preserve the full TuShare payload. DuckDB keeps `raw_payload`; Mongo stores the full document directly.

**Sync Shape**
- `stk_holdernumber`: pull by full-market `start_date/end_date` windows and paginate.
- `top10_holders` / `top10_floatholders`: pull by full-market `ann_date` windows and paginate.
- Sync progress is recorded in `data_sync_date`.

**Storage Keys**
- DuckDB `stk_holdernumber`: upsert by `ts_code + end_date`
- Mongo `top10_holders`: unique index on `ts_code + end_date + holder_name`
- Mongo `top10_floatholders`: unique index on `ts_code + end_date + holder_name`

**First Delivery**
- Add TuShare client fetchers
- Add DuckDB/Mongo persistence helpers
- Add two daily sync scripts
- Add targeted tests
- Run first real sync for recent history
