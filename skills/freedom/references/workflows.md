# Workflows

Map market questions to Freedom API workflows.

## Verify Connectivity

1. Read `auth.md`.
2. Confirm auth and the latest trade date.
3. Stop if auth or date resolution fails.

## Search A Stock

Use when the user provides a code, partial code, or company name.

1. Call `GET /stocks/search`.
2. Normalize to `ts_code`.
3. Continue with quote, indicator, or financial workflows.

## Market Snapshot

Use when the user asks:

- "今天市场怎么样"
- "Show today's movers"
- "Give me a daily snapshot"

Flow:

1. Resolve the latest trade date.
2. Call `GET /stocks/daily/snapshot`.
3. Narrow with filters or fields when the request is specific.

## Sector Ranking

Use when the user asks for industry strength, weakness, or rotation.

1. Resolve the trade date.
2. Call `GET /industry/shenwan/daily/ranking`.
3. Fetch members only when the user wants drill-down into a winning or losing industry.

## Stock Screening

Use when the user wants a screened universe.

1. Choose the correct screen type:
   - price or streak behavior -> `POST /stocks/daily/stats/screen`
   - valuation or turnover -> `GET /stocks/daily-basic/snapshot`
   - financial quality -> `GET /stocks/financials/indicators/screen`
   - dividends -> `GET /stocks/dividends/screen`
2. Normalize dates, industry filters, and pagination.

## Company Deep Dive

Use when the user wants a company view.

1. Search or confirm the `ts_code`.
2. Pull recent price data and indicators.
3. Pull financial statements or summaries.
4. Add dividends, insider trades, and events if relevant.

## Macro Or Event Context

Use macro endpoints for market context and event endpoints for catalyst checks.
Treat empty event datasets as "no current records found", not as transport failure.
