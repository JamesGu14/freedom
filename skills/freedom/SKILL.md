---
name: freedom
description: Operate the Freedom market data and analysis domain for A-share stock lookup, daily snapshots, industry rankings, financial indicators, dividends, insider trades, macro series, and watchlist-style workflows. Use when an agent needs market data, screening, sector ranking, company detail, or other Freedom API workflows.
---

# Freedom

Use this skill to operate the Freedom market data domain through its API and analysis workflows instead of guessing route names or response conventions.

## Ground Rules

- Read `references/auth.md` before making authenticated calls.
- Read `references/workflows.md` when the user asks for a market task such as ranking sectors, screening stocks, or checking a company's financials.
- Read `references/endpoints.md` for the high-frequency endpoint map.
- Read `references/api-conventions.md` before combining multiple market datasets.

## Deployment Placeholders

- `{{BASE_URL}}`: mounted app root, for example `https://example.com/freedom`
- `{{OPENAPI_URL}}`: OpenAPI document URL
- `{{API_PREFIX}}`: external API prefix
- `{{BEARER_TOKEN}}`: internal API token or equivalent service token

Keep real domains, usernames, passwords, and tokens out of redistributable variants.

## Operating Pattern

1. Verify auth before any non-public workflow.
2. Resolve the latest trade date when recency matters.
3. Prefer high-frequency market endpoints before expensive or niche detail endpoints.
4. Treat empty datasets as a valid business result unless the API explicitly reports an error.
5. Normalize user input into `ts_code`, date ranges, and industry codes before making screening calls.

## Reference Files

- `references/auth.md`: auth and connectivity checks
- `references/endpoints.md`: high-frequency endpoint map for Freedom
- `references/workflows.md`: market-analysis playbooks
- `references/api-conventions.md`: response rules, symbol formats, and fallback behavior
