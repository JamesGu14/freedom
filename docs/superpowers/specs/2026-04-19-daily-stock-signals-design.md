# Daily Stock Signals Page and Pipeline Design

## Goal

Build a daily stock signals system that, after daily market data and factor data finish syncing, computes buy/sell technical signals for the current trade date, stores the results in MongoDB, supports backfilling the past year of signal history, and exposes a frontend page for date-based review.

The first release is intentionally limited to technical signals derived from existing `daily` Parquet data, `indicators` Parquet data, and `stock_basic` MongoDB metadata.

## Scope

### In scope

1. A new daily derived-data task that computes stock signals.
2. Airflow integration for daily incremental generation.
3. A backfill mode that can populate the last 365 days of history.
4. MongoDB persistence for signal groups and resonance groups.
5. Backend APIs for signal dates, overview, and signal-type detail.
6. A frontend page for date-based review of buy signals, sell signals, and resonance sections.

### Out of scope for v1

1. Short-term resistance/support level storage or display.
2. Push notifications.
3. Signal outcome statistics or backtest performance overlays.
4. Capital-flow, northbound, financing, or shareholder-composite signals.
5. Auto-generated signal commentary.
6. Per-stock history pages or rich stock-detail integrations beyond simple list navigation.

## Current System Context

### Relationship to existing signal pages and APIs

The repository already contains an older signal stack based on `daily_signal` and `strategy_signals`.

This new feature is intentionally a **separate system** with its own storage model, API routes, and frontend page.

For v1:

1. Do **not** replace or extend the existing `/daily-signals` routes.
2. Do **not** reuse the existing `daily_signal` Mongo collection.
3. Use a new route family and a new frontend page dedicated to daily stock signals.

### Relevant daily Airflow DAG

The market-data DAG is `freedom_market_data_daily`.

- Schedule: `30 20 * * 1-5`
- Timezone: `Asia/Shanghai`
- It first runs `precheck_trade_day`
- Main groups:
  - `market_core`
  - `factor_and_flow`
  - `financials_and_corporate`
  - `holders_and_margin`
  - `index_and_industry`
- Dependency today:
  - `market_core -> factor_and_flow`
- `finalize_run` collects result counts at the end.

### Existing data sources needed for v1

1. `data/raw/daily/ts_code=*/year=*/part-*.parquet`
   - Used for close, high, pct change, recent rolling windows, and breakout/breakdown detection.
2. `data/features/indicators/ts_code=*/year=*/part-*.parquet`
   - Used for MA, MACD, KDJ, RSI, Bollinger, ATR, volume ratio, and related daily indicators.
3. MongoDB `stock_basic`
   - Used to enrich signal output with stock name and industry.

These fields are already present and sufficient for the first batch of technical signals.

## Product Design

### Primary user experience

The page is a daily review page with history lookup.

The default behavior is:

1. Open the newest available trade date.
2. Show summary counts.
3. Show buy and sell signal sections separately.
4. Show resonance sections separately.
5. Allow switching to historical dates.

### Page layout

Suggested route:

- `frontend/pages/daily-stock-signals.js`

This page is separate from the existing:

- `frontend/pages/daily-signals.js`
- `frontend/pages/daily-signals-legacy.js`

Those older pages remain untouched in v1.

Sections:

1. **Top filter bar**
   - Trade date selector.
2. **Summary area**
   - Buy signal hit count.
   - Sell signal hit count.
   - Buy resonance count.
   - Sell resonance count.
3. **Buy signal section**
   - One card per buy signal type.
4. **Sell signal section**
   - One card per sell signal type.
5. **Resonance section**
   - Buy resonance column.
   - Sell resonance column.
   - Each split into normal / strong / very strong.

### Stock display fields in v1

Each stock row should include:

- `ts_code`
- `name`
- `industry`
- `close`
- `pct_chg`
- `volume_ratio`
- same-side signal count
- signal-specific metrics snapshot

### Duplicate display rule

If a stock hits multiple same-side signals on the same date:

1. It remains visible in each original signal card.
2. It also appears in the resonance section.

This preserves raw signal visibility while surfacing higher-confidence overlaps.

### Sorting rule

For stock lists in signal cards and resonance sections:

1. Sort by signal strength first.
   - `4+` same-side signals
   - then `3`
   - then `2`
   - then single signal
2. Tie-break by volume/breakout strength.
3. Tie-break by daily `pct_chg`.

## Signal Definitions

The first release contains 8 technical signals.

## Signal Calculation Conventions

### Price basis

Signal computation must use a consistent adjusted-price basis.

For v1:

1. Use **`close_qfq`** as the price basis for signal computation wherever price comparisons are involved.
2. Use the indicator-derived adjusted-price context for breakout and breakdown calculations as well.
3. The frontend may still display raw `close` for user familiarity, but signal triggering logic must be based on adjusted-price inputs.

### Cross detection rule

All cross-type signals must use the same event rule:

- A bullish cross means:
  - today's fast line `>` today's slow line
  - and previous day's fast line `<=` previous day's slow line
- A bearish cross means:
  - today's fast line `<` today's slow line
  - and previous day's fast line `>=` previous day's slow line

Applied to v1:

1. **MACD golden cross**
   - `today.macd > today.macd_signal`
   - `prev.macd <= prev.macd_signal`
2. **MACD dead cross**
   - `today.macd < today.macd_signal`
   - `prev.macd >= prev.macd_signal`
3. **KDJ golden cross**
   - `today.kdj_k > today.kdj_d`
   - `prev.kdj_k <= prev.kdj_d`
4. **KDJ dead cross**
   - `today.kdj_k < today.kdj_d`
   - `prev.kdj_k >= prev.kdj_d`

### Buy signals

1. **`buy_macd_kdj_double_cross`**
   - Today MACD golden cross.
   - Today KDJ golden cross.
   - Both must happen on the same trade date.

2. **`buy_ma_bullish_formation`**
   - Today: `ma5 > ma10 > ma20 > ma60`
   - Previous trade date did not satisfy this full ordering.
   - This captures formation, not persistent state.

3. **`buy_volume_breakout_20d`**
   - Today adjusted close breaks above the previous 20-trade-date adjusted-close high.
   - `volume_ratio > 1.5`

4. **`buy_rsi_rebound`**
   - Today `rsi6 > rsi12`
   - Previous trade date `rsi6 <= rsi12`
   - Previous `rsi6` must be in oversold territory.
   - Default v1 threshold: previous `rsi6 < 30`

### Sell signals

5. **`sell_macd_kdj_double_cross`**
   - Today MACD dead cross.
   - Today KDJ dead cross.

6. **`sell_ma_bearish_formation`**
   - Today: `ma5 < ma10 < ma20 < ma60`
   - Previous trade date did not satisfy this full ordering.

7. **`sell_volume_breakdown_20d`**
   - Today adjusted close breaks below the previous 20-trade-date adjusted-close low.
   - `volume_ratio > 1.5`

8. **`sell_rsi_fall`**
   - Today `rsi6 < rsi12`
   - Previous trade date `rsi6 >= rsi12`
   - Previous `rsi6` must be in overbought territory.
   - Default v1 threshold: previous `rsi6 > 70`

## Resonance Rules

Resonance is computed by side, never by mixing buy and sell signals.

For each stock on a given `trade_date`:

- Count how many **buy** signals it hit.
- Count how many **sell** signals it hit.

Levels:

- `normal`: 2 signals
- `strong`: 3 signals
- `very_strong`: 4 or more signals

The page should show buy resonance and sell resonance separately.

## Data Pipeline Design

### New task placement in Airflow

Add a new task group:

- `signals_and_screeners`

Add a new task:

- `generate_daily_stock_signals`

Suggested dependency graph:

```text
market_core -> factor_and_flow -> signals_and_screeners
market_core -------------------> signals_and_screeners
signals_and_screeners -> finalize_run
```

Rationale:

- `market_core` provides daily market data.
- `factor_and_flow` provides `sync_stk_factor_pro`, which is required for `indicators`.
- This new task is a downstream derived-data computation, not a raw data sync.

This design keeps the DAG semantically clean and leaves room for future screeners.

### Execution command shape

Keep the same registry pattern used by other tasks:

```bash
python backend/scripts/daily/generate_daily_stock_signals.py --start-date <trade_date> --end-date <trade_date>
```

### Core module and script split

#### Core module

Suggested new module:

- `backend/app/signals/daily_stock_signals.py`

Responsibilities:

1. Load the needed date window.
2. Join/enrich daily and indicator rows.
3. Compute signal matches for the target date.
4. Compute same-side resonance.
5. Produce normalized MongoDB documents.

#### Script entrypoint

Suggested new script:

- `backend/scripts/daily/generate_daily_stock_signals.py`

Responsibilities:

1. Parse CLI arguments.
2. Resolve target date or date range.
3. Call the core module.
4. Upsert signal docs and resonance docs.
5. Log summary counts.

## Backfill Design

The system must support both daily incremental generation and one-time historical backfill.

### Required modes

1. **Single date**

```bash
python backend/scripts/daily/generate_daily_stock_signals.py --trade-date 20260419
```

2. **Date range**

```bash
python backend/scripts/daily/generate_daily_stock_signals.py --start-date 20250419 --end-date 20260419
```

3. **Last N days**

```bash
python backend/scripts/daily/generate_daily_stock_signals.py --last-days 365
```

For v1, `--last-days 365` means:

- the most recent **365 natural days** as the requested range
- then map that range to open trading days only

### Historical backfill requirement

The initial rollout must populate roughly the last 1 year of results.

### Trading-day resolution rule

The script must resolve requested date ranges to actual open trading days before computing or writing results.

Rules:

1. Only open trading days are processed.
2. Non-trading days are skipped and do not generate output documents.
3. Date availability for the page is determined by stored signal results, not by the full trade calendar.

### Windowing rule

Although the output is per target date, the computation must fetch enough lookback data for stable calculations.

For v1, use at least a **60-trade-date lookback window** before each target date so that:

- 20-day breakout/breakdown works correctly.
- Previous-day cross checks work correctly.
- MA formation checks are not edge-truncated.
- RSI rebound/fall checks have sufficient context.

Only the requested target date(s) are written back to MongoDB.

## MongoDB Data Model

Use two collections in v1.

### Collection 1: `daily_stock_signals`

One document per:

- `trade_date`
- `signal_type`

Example shape:

```json
{
  "trade_date": "20260419",
  "signal_type": "buy_macd_kdj_double_cross",
  "signal_side": "buy",
  "count": 32,
  "stocks": [
    {
      "ts_code": "000001.SZ",
      "name": "平安银行",
      "industry": "银行",
      "close": 11.01,
      "pct_chg": 1.23,
      "volume_ratio": 1.81,
      "signal_count_same_side": 3,
      "sort_score": {
        "strength_rank": 3,
        "volume_rank_value": 1.81,
        "pct_chg_rank_value": 1.23
      },
      "metrics": {
        "macd": 0.12,
        "macd_signal": 0.08,
        "kdj_k": 45.3,
        "kdj_d": 41.2,
        "ma5": 11.2,
        "ma10": 11.0,
        "ma20": 10.8,
        "ma60": 10.35,
        "rsi6": 31.2,
        "rsi12": 28.4
      }
    }
  ],
  "created_at": "2026-04-19T20:45:00+08:00",
  "updated_at": "2026-04-19T20:45:00+08:00",
  "signal_version": "v1"
}
```

Indexes:

1. Unique: `(trade_date, signal_type)`
2. Query index: `(trade_date, signal_side)`

### Collection 2: `daily_stock_signal_resonance`

One document per:

- `trade_date`
- `signal_side`
- `resonance_level`

Example shape:

```json
{
  "trade_date": "20260419",
  "signal_side": "buy",
  "resonance_level": "strong",
  "min_signal_count": 3,
  "count": 8,
  "stocks": [
    {
      "ts_code": "000001.SZ",
      "name": "平安银行",
      "industry": "银行",
      "close": 11.01,
      "pct_chg": 1.23,
      "volume_ratio": 1.81,
      "signal_count": 3,
      "signal_types": [
        "buy_macd_kdj_double_cross",
        "buy_ma_bullish_formation",
        "buy_volume_breakout_20d"
      ]
    }
  ],
  "created_at": "2026-04-19T20:45:00+08:00",
  "updated_at": "2026-04-19T20:45:00+08:00",
  "signal_version": "v1"
}
```

Indexes:

1. Unique: `(trade_date, signal_side, resonance_level)`

### Empty-document policy

Persist empty documents for every processed trade date even when a signal or resonance bucket has zero hits.

Per processed date, v1 should persist:

1. 8 signal documents
2. 6 resonance documents

with `count = 0` and `stocks = []` where applicable.

This is a deliberate API and frontend simplification choice.

## Write Semantics

MongoDB writes must be idempotent.

Use replace/upsert semantics keyed by the unique dimensions above.

This is required so that:

1. Airflow reruns are safe.
2. Backfill reruns are safe.
3. Signal rule changes can be reapplied to historical ranges.

## Backend API Design

### 1. Signal dates list

`GET /api/daily-stock-signals/dates`

Purpose:

- Return available trade dates with signal results.

Definition:

- Dates are derived from actual persisted result documents in `daily_stock_signals`.
- This endpoint must not synthesize dates from the trade calendar alone.

### 2. Main overview endpoint

`GET /api/daily-stock-signals/overview?trade_date=20260419`

Response shape:

```json
{
  "trade_date": "20260419",
  "buy_signals": [
    {
      "signal_type": "buy_macd_kdj_double_cross",
      "signal_side": "buy",
      "count": 32,
      "stocks": []
    }
  ],
  "sell_signals": [
    {
      "signal_type": "sell_rsi_fall",
      "signal_side": "sell",
      "count": 18,
      "stocks": []
    }
  ],
  "buy_resonance": [
    {
      "resonance_level": "strong",
      "count": 8,
      "stocks": []
    }
  ],
  "sell_resonance": [
    {
      "resonance_level": "normal",
      "count": 11,
      "stocks": []
    }
  ]
}
```

This is the primary page API.

Default response-size rule for v1:

1. Each signal group returns the top 50 stocks by stored sort order.
2. Each resonance bucket returns the top 50 stocks by stored sort order.
3. Full lists are retrieved through the by-type endpoint.

### 3. Single signal detail

`GET /api/daily-stock-signals/by-type?trade_date=20260419&signal_type=buy_macd_kdj_double_cross`

Purpose:

- Return a single signal group document for expanded viewing or future drill-down.

This endpoint is the full-detail path and is expected to return the complete stored stock list for the selected signal type.

### API behavior notes

1. If `trade_date` is omitted in the overview API, it may default to the latest available date.
2. Results should already be stored in display order so frontend sorting is minimal.
3. The API does not need to compute signals at request time.

## Frontend Behavior

### Suggested page route

- `frontend/pages/daily-stock-signals.js`

### Loading behavior

1. Load available dates.
2. Select the latest available date by default.
3. Fetch overview data.
4. Render buy/sell/resonance blocks.

### Section structure

1. Date selector.
2. Summary cards.
3. Buy signal cards.
4. Sell signal cards.
5. Buy resonance blocks.
6. Sell resonance blocks.

### v1 simplifications

Do not include in v1:

- inline charts
- push actions
- signal commentary generation
- resistance/support overlays
- signal performance overlays

## Error Handling

### Script-level handling

1. Missing Parquet directories for a target date should not crash the whole range run without a clear error message.
2. If a date has no qualifying stocks for a signal, persist an empty group document with `count=0` or explicitly define that empty groups are omitted. Recommendation: persist empty groups for consistency in page rendering.
3. If enrichment data from `stock_basic` is missing for a stock, still keep the stock using `ts_code` and leave optional fields null.
4. If a stock triggers both buy-side and sell-side signals on the same trade date, keep both results. No conflict-resolution suppression is applied in v1.

### Resonance buckets per date

- buy/normal
- buy/strong
- buy/very_strong
- sell/normal
- sell/strong
- sell/very_strong

## Testing Strategy

### Unit-level

1. Signal rule tests for each of the 8 signals.
2. Resonance classification tests.
3. Sorting tests.
4. Date window and lookback boundary tests.

### Integration-level

1. Script test for one date using existing Parquet inputs.
2. Range backfill test for a small historical interval.
3. Mongo upsert idempotency test.
4. API response shape test.
5. Confirm empty docs are written for zero-hit signal types and resonance buckets.
6. Confirm same-stock buy/sell conflicts can coexist in stored output.

### Airflow-level

1. Confirm task registration in `daily_sync_registry`.
2. Confirm DAG dependency placement in `freedom_market_data_daily`.
3. Confirm daily execution uses the same date argument contract as existing tasks.

## Implementation Boundaries

### Must deliver in v1

1. Daily signal script.
2. Daily Airflow task integration.
3. One-year backfill support.
4. Two Mongo collections.
5. Three APIs.
6. One frontend page.

### Must not expand in v1

1. No resistance/support computation.
2. No signal push notification workflow.
3. No signal outcome analytics.
4. No funds/holder/composite signals.
5. No third collection for per-stock signal history.

## Recommended Delivery Sequence

1. Build the core signal computation module.
2. Build Mongo persistence.
3. Build the CLI script with range/backfill support.
4. Register and wire the Airflow task.
5. Add backend APIs.
6. Build the frontend page.
7. Run one-year historical backfill.

### Backfill implementation strategy

For historical ranges, prefer bulk interval computation over repeated day-by-day full-market rereads.

Recommended approach:

1. Read the requested range plus lookback buffer in larger batches.
2. Group by stock in memory.
3. Compute signal states by date per stock.
4. Emit stored docs only for the requested target trade dates.

This is the preferred v1 implementation strategy for the one-year backfill.

## Open Decisions Resolved in This Design

The following have been explicitly decided:

1. Page supports both latest view and historical date lookup.
2. Stocks remain in original signal cards and resonance sections.
3. Resonance uses 2 / 3 / 4+ tiers.
4. Sorting prioritizes signal strength first.
5. Historical backfill for the last year is part of the first release.
6. The feature is implemented as a downstream Airflow task group, not embedded into raw sync groups.
7. New routes and page are separate from the old daily-signal stack.
8. Computation uses adjusted-price basis (`close_qfq`) for signal logic.
9. `--last-days` is defined on natural-day range, then mapped to trading days.
10. Empty docs are persisted for zero-hit signal and resonance groups.
11. Overview is intentionally capped to top 50 per group.
12. Same-day buy/sell conflicts are allowed to coexist.

## Approval Gate

This design is ready for implementation planning once reviewed and approved.
