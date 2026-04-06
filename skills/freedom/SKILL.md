---
name: freedom
description: Operate the Freedom market data and analysis domain through the current `/freedom/api` routes with centralized authentication delegated to `personal-authenticator`. Use when OpenClaw or another agent needs A-share market data, screening, sector ranking, company detail, macro context, or other Freedom API workflows.
---

# Freedom

Use this skill to operate the Freedom market data domain through its API and analysis workflows instead of guessing route names or response conventions.

## Ground Rules

- Read `references/auth.md` before making authenticated calls.
- Read `references/workflows.md` when the user asks for a market task such as ranking sectors, screening stocks, or checking a company's financials.
- Read `references/endpoints.md` for the high-frequency endpoint map.
- Read `references/api-conventions.md` before combining multiple market datasets.

## Runtime Values

- `{{BASE_URL}}`: mounted app root, usually `https://www.jamesgu.cn/freedom`
- `{{OPENAPI_URL}}`: usually `https://www.jamesgu.cn/freedom/api/openapi.json`
- `{{API_PREFIX}}`: usually `https://www.jamesgu.cn/freedom/api`
- `{{BEARER_TOKEN}}`: `personal-authenticator` access token or a `james`-owned API Key

## Operating Pattern

1. Verify auth before any non-public workflow.
2. Treat `/auth/login` as a proxied browser entrypoint; OpenClaw should normally start with an existing bearer token.
3. Resolve the latest trade date when recency matters.
4. Prefer high-frequency market endpoints before expensive or niche detail endpoints.
5. Treat empty datasets as a valid business result unless the API explicitly reports an error.
6. Normalize user input into `ts_code`, date ranges, and industry codes before making screening calls.

## Reference Files

- `references/auth.md`: auth and connectivity checks
- `references/endpoints.md`: high-frequency endpoint map for Freedom
- `references/workflows.md`: market-analysis playbooks
- `references/api-conventions.md`: response rules, symbol formats, and fallback behavior
