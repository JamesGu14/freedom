# Research Data Center Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a dedicated research data center UI and `research/*` aggregation APIs so all currently-ingested but underexposed TuShare datasets become visible in the frontend and consumable by OpenClaw.

**Architecture:** Add a new aggregation layer in the FastAPI backend that composes existing raw data sources into stable research-oriented payloads, then build a separate research section in the frontend with stock and market research pages. Keep existing raw APIs intact and use the new research APIs for UI and agent consumption.

**Tech Stack:** FastAPI, MongoDB, DuckDB, Next.js Pages Router, existing `apiFetch` client, Pytest, Next.js build.

---

### Task 1: Add research route skeleton

**Files:**
- Create: `backend/app/api/routes/research.py`
- Modify: `backend/app/api/routes/__init__.py`
- Modify: `backend/app/api/routers.py`
- Test: `backend/tests/api/test_research_api.py`

**Step 1: Write the failing test**

Add tests that expect:

- `GET /api/research/stocks/000001.SZ/overview`
- `GET /api/research/stocks/000001.SZ/financials`
- `GET /api/research/market/indexes`

to be routable.

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/api/test_research_api.py -q`  
Expected: `404` or import failure.

**Step 3: Write minimal implementation**

- Create a new router file with placeholder endpoints.
- Register router in route exports and aggregated router tree.

**Step 4: Run test to verify it passes**

Run: `pytest backend/tests/api/test_research_api.py -q`  
Expected: PASS.

### Task 2: Add stock research overview aggregation

**Files:**
- Create: `backend/app/services/research_service.py`
- Modify: `backend/app/api/routes/research.py`
- Test: `backend/tests/services/test_research_service.py`

**Step 1: Write the failing test**

Test that stock overview payload includes:

- `basic`
- `latest_daily`
- `latest_daily_basic`
- `latest_indicators`
- `latest_financial_indicator`
- `latest_dividend_summary`
- `latest_holder_summary`
- `latest_flow_summary`
- `latest_event_summary`

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/services/test_research_service.py -q`

**Step 3: Write minimal implementation**

- Aggregate data from existing Mongo/DuckDB/raw services.
- Normalize missing values to `null` instead of raising.

**Step 4: Run test to verify it passes**

Run: `pytest backend/tests/services/test_research_service.py -q`

### Task 3: Add stock financials aggregation API

**Files:**
- Modify: `backend/app/services/research_service.py`
- Modify: `backend/app/api/routes/research.py`
- Test: `backend/tests/services/test_research_service.py`

**Step 1: Write the failing test**

Add test for `/api/research/stocks/{ts_code}/financials` expecting:

- `indicators`
- `income`
- `balance`
- `cashflow`
- `latest_period`
- `periods`

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/services/test_research_service.py -q`

**Step 3: Write minimal implementation**

- Reuse current financial query logic from `agent_required_api.py`.
- Normalize output for frontend tabs.

**Step 4: Run test to verify it passes**

Run: `pytest backend/tests/services/test_research_service.py -q`

### Task 4: Add dividends, holders, flows, and events aggregation APIs

**Files:**
- Modify: `backend/app/services/research_service.py`
- Modify: `backend/app/api/routes/research.py`
- Test: `backend/tests/services/test_research_service.py`

**Step 1: Write the failing test**

Add tests for:

- `/api/research/stocks/{ts_code}/dividends`
- `/api/research/stocks/{ts_code}/holders`
- `/api/research/stocks/{ts_code}/flows`
- `/api/research/stocks/{ts_code}/events`

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/services/test_research_service.py -q`

**Step 3: Write minimal implementation**

- Build summary blocks plus raw list sections.
- For holders and flows, use existing collections and query helpers.
- For events, start with `suspend_d` and `stk_surv`.

**Step 4: Run test to verify it passes**

Run: `pytest backend/tests/services/test_research_service.py -q`

### Task 5: Add market research aggregation APIs

**Files:**
- Modify: `backend/app/services/research_service.py`
- Modify: `backend/app/api/routes/research.py`
- Test: `backend/tests/services/test_research_service.py`

**Step 1: Write the failing test**

Add tests for:

- `/api/research/market/indexes`
- `/api/research/market/indexes/{ts_code}`
- `/api/research/market/sectors`
- `/api/research/market/hsgt-flow`

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/services/test_research_service.py -q`

**Step 3: Write minimal implementation**

- Provide tracked index list based on current `index_daily` whitelist.
- Aggregate `index_basic`, `index_daily`, `market_index_dailybasic`, `index_factor_pro`.
- Aggregate sector snapshots and HSGT flow.

**Step 4: Run test to verify it passes**

Run: `pytest backend/tests/services/test_research_service.py -q`

### Task 6: Add frontend research landing page

**Files:**
- Create: `frontend/pages/research/index.js`
- Modify: `frontend/pages/_app.js`
- Modify: `frontend/styles/globals.css`
- Test: build via `npm run build`

**Step 1: Write the failing test**

There is no formal frontend test setup. Use build-time validation as the failing check.

**Step 2: Run build to verify it fails after adding empty route import expectations**

Run: `npm run build`

**Step 3: Write minimal implementation**

- Create research landing page with entry cards for stock research and market research.
- Add sidebar or navigation entry.

**Step 4: Run build to verify it passes**

Run: `npm run build`

### Task 7: Add stock research page shell

**Files:**
- Create: `frontend/pages/research/stocks/[ts_code].js`
- Modify: `frontend/lib/api.js` if helper wrappers are needed
- Modify: `frontend/styles/globals.css`
- Test: `npm run build`

**Step 1: Write the failing test**

Use build-time validation.

**Step 2: Run build to verify it fails**

Run: `npm run build`

**Step 3: Write minimal implementation**

- Fetch `/api/research/stocks/{ts_code}/overview`
- Render summary cards and section tabs
- Add placeholders for financials, holders, flows, events

**Step 4: Run build to verify it passes**

Run: `npm run build`

### Task 8: Fill stock research sections

**Files:**
- Modify: `frontend/pages/research/stocks/[ts_code].js`
- Modify: `frontend/styles/globals.css`
- Test: `npm run build`

**Step 1: Write the failing test**

Use build-time validation plus backend integration smoke if needed.

**Step 2: Run build**

Run: `npm run build`

**Step 3: Write minimal implementation**

- Add financials and dividends section
- Add holders and chips section
- Add flows section
- Add events section

**Step 4: Run build to verify it passes**

Run: `npm run build`

### Task 9: Add market research page

**Files:**
- Create: `frontend/pages/research/market.js`
- Modify: `frontend/styles/globals.css`
- Test: `npm run build`

**Step 1: Write the failing test**

Use build-time validation.

**Step 2: Run build**

Run: `npm run build`

**Step 3: Write minimal implementation**

- Render tracked indexes snapshot
- Render index detail selector
- Render sector and HSGT summary placeholders

**Step 4: Run build to verify it passes**

Run: `npm run build`

### Task 10: Link stock detail page to research center

**Files:**
- Modify: `frontend/pages/stocks/[ts_code].js`
- Test: `npm run build`

**Step 1: Write the failing test**

Use build-time validation.

**Step 2: Run build**

Run: `npm run build`

**Step 3: Write minimal implementation**

- Add a visible link or button from stock detail page to `/research/stocks/{ts_code}`

**Step 4: Run build to verify it passes**

Run: `npm run build`

### Task 11: Add OpenClaw-facing API docs

**Files:**
- Modify: `README.md`
- Modify: `docs/tushare_5000积分接口实现对照.md`
- Create: `docs/plans/2026-03-15-research-data-center-api.md`

**Step 1: Write the failing test**

Documentation task; no code-level test.

**Step 2: Write minimal implementation**

- Document `research/*` endpoints
- Document intended OpenClaw resource grouping
- Clarify raw API vs research API usage

**Step 3: Verify**

- Review rendered Markdown
- Ensure paths and endpoint names match implementation

### Task 12: Full verification and deployment

**Files:**
- Modify any touched files as needed from review

**Step 1: Run backend tests**

Run: `pytest backend/tests/api/test_research_api.py backend/tests/services/test_research_service.py -q`

**Step 2: Run existing targeted regressions**

Run: `pytest backend/tests/services/test_data_sync_service.py backend/tests/api/test_data_sync_api.py -q`

**Step 3: Run frontend production build**

Run: `npm run build`

**Step 4: Restart services if needed**

Run:

```bash
docker compose up -d --build backend frontend nginx
```

**Step 5: Smoke check**

- Verify `/freedom/research`
- Verify `/freedom/research/stocks/<ts_code>`
- Verify `/freedom/research/market`
- Verify `/freedom/api/research/*`

