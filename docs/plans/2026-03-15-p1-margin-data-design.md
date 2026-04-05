# P1 Margin Data Design

## Scope

- `margin`
- `margin_detail`

## Storage

- `margin` -> MongoDB collection `margin`
- `margin_detail` -> DuckDB table `margin_detail`

## Why

- `margin` is a small market-level daily aggregate keyed by `trade_date + exchange_id`, which fits MongoDB well and preserves the TuShare payload without extra schema overhead.
- `margin_detail` is a stock-level daily table keyed by `trade_date + ts_code`, which is better suited to DuckDB for later joins, screening, and analytical queries.

## Sync shape

- `margin`: pull by date windows using `start_date/end_date` and paginate.
- `margin_detail`: pull by shorter date windows using `start_date/end_date` and paginate, because row counts can hit page limits quickly.

## Keys

- Mongo `margin`: unique index on `trade_date + exchange_id`
- DuckDB `margin_detail`: upsert by `trade_date + ts_code`

## Payload preservation

- `margin` stores the full TuShare record directly in Mongo.
- `margin_detail` stores core query columns plus `raw_payload`, so every returned TuShare field is retained.

## Initial backfill strategy

- First sync a recent practical range to validate throughput and storage shape.
- After the first successful run, decide whether to extend the history further back.
