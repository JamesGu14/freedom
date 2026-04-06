# P1 Dividend Data Design

## Scope

- TuShare `dividend`
- Local MongoDB collection `dividend_history`

## Why use `dividend_history`

- The repository already has API routes that read `dividend_history`.
- At the start of this work there was no writer for that collection and it was empty.
- Reusing `dividend_history` avoids creating another parallel dividend table.

## Storage

- `dividend` raw data -> MongoDB collection `dividend_history`

## Key choice

- Unique key: `ts_code + end_date + ann_date + div_proc`

This preserves multiple stages such as proposals and implementations for the same report period.

## Payload preservation

- Preserve all TuShare-returned fields directly in the document.
- Normalize date fields to `YYYYMMDD`.
- Add `updated_at`.

## Derived fields policy

- First phase does **not** attempt to fully derive `dv_ratio`, `payout_ratio`, `consecutive_years`, or other screening metrics.
- Existing API readers can already tolerate missing derived metrics.
- Future phase can enrich `dividend_history` by joining prices, share counts, and financial statements.

## Initial backfill strategy

- Query TuShare by concrete `ann_date`, not by generic `start_date/end_date`
- Prefer the real `ann_date` set already present in local financial tables, instead of blindly scanning every calendar day
- Keep a simple paginated sync script
- First practical backfill range: `20240101 ~ 20260315`
- Current first-pass local result:
  - `43174` documents
  - `ann_date` range `20240104 ~ 20260314`
  - `end_date` range `20230930 ~ 20260116`

## Follow-up todo

- Add a second-stage enrichment job for `dividend_history`:
  - `dv_ratio`
  - `payout_ratio`
  - `consecutive_years`
  - richer dividend summary fields for screening
- Extend `dividend_history` history further back once the recent practical range is stable and useful
