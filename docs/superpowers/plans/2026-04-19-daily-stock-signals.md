# Daily Stock Signals Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a new daily stock signals pipeline that computes 8 technical buy/sell signals from existing Parquet data, stores grouped results in MongoDB, serves a new `/daily-stock-signals` API/page, integrates into the daily Airflow DAG, and backfills the last year of results.

**Architecture:** Add a focused backend signal-computation module that reads `daily` + `indicators` + `stock_basic`, emits two Mongo document shapes (signal groups and resonance groups), and is called by a new daily script. Expose a dedicated API route family and a dedicated frontend page, then wire the script into `DAILY_SYNC_TASKS` and `freedom_market_data_daily` as a downstream `signals_and_screeners` group.

**Tech Stack:** FastAPI, MongoDB/PyMongo, DuckDB query engine over Parquet, pandas, Next.js Pages Router, React, Airflow.

---

## File Structure

### New files
- `backend/app/signals/daily_stock_signals.py` — core computation logic and document builders.
- `backend/app/data/mongo_daily_stock_signals.py` — indexes and upsert/query helpers for `daily_stock_signals` and `daily_stock_signal_resonance`.
- `backend/app/services/daily_stock_signals_service.py` — read-side service functions for dates/overview/by-type.
- `backend/app/api/routes/daily_stock_signals.py` — dedicated API routes.
- `backend/scripts/daily/generate_daily_stock_signals.py` — CLI entrypoint for single-date/range/last-days generation and backfill.
- `backend/tests/services/test_daily_stock_signals_service.py` — service-level tests.
- `backend/tests/api/test_daily_stock_signals_api.py` — route tests.
- `backend/tests/scripts/test_generate_daily_stock_signals.py` — script/date-resolution/idempotency tests.
- `backend/tests/signals/test_daily_stock_signals.py` — core signal-rule and resonance tests.
- `frontend/pages/daily-stock-signals.js` — new signal page.

### Modified files
- `backend/app/api/routes/__init__.py` — export the new router.
- `backend/app/api/routers.py` — include the new router under auth.
- `backend/app/airflow_sync/daily_sync_registry.py` — register `generate_daily_stock_signals` under new group.
- `backend/airflow/dags/freedom_market_data_daily.py` — add `signals_and_screeners` group and dependencies.
- `backend/tests/airflow/test_daily_sync_registry.py` — include the new group/task expectations.
- `backend/tests/airflow/test_freedom_market_data_daily.py` — verify DAG group wiring.
- `frontend/styles/globals.css` or the existing page style location used by `daily-signals.js` — add page styles only if needed.

---

### Task 1: Add the core signal computation module

**Files:**
- Create: `backend/app/signals/daily_stock_signals.py`
- Test: `backend/tests/signals/test_daily_stock_signals.py`

- [ ] **Step 1: Write the failing core signal tests**

Add tests that lock in the approved rules:

```python
from app.signals.daily_stock_signals import (
    compute_signal_flags_for_stock,
    classify_resonance_level,
)


def test_macd_kdj_double_cross_buy_requires_both_crosses_same_day() -> None:
    rows = [
        {"trade_date": "20260416", "macd": 0.1, "macd_signal": 0.2, "kdj_k": 20.0, "kdj_d": 25.0},
        {"trade_date": "20260417", "macd": 0.3, "macd_signal": 0.2, "kdj_k": 30.0, "kdj_d": 25.0},
    ]

    result = compute_signal_flags_for_stock(rows, target_date="20260417")

    assert result["buy_macd_kdj_double_cross"] is True
    assert result["sell_macd_kdj_double_cross"] is False


def test_buy_ma_bullish_formation_only_triggers_on_formation_day() -> None:
    rows = [
        {"trade_date": "20260416", "ma5": 10.0, "ma10": 9.9, "ma20": 10.1, "ma60": 9.5},
        {"trade_date": "20260417", "ma5": 10.3, "ma10": 10.1, "ma20": 9.9, "ma60": 9.5},
    ]

    result = compute_signal_flags_for_stock(rows, target_date="20260417")

    assert result["buy_ma_bullish_formation"] is True


def test_breakout_uses_close_qfq_and_volume_ratio_threshold() -> None:
    rows = [
        {"trade_date": "20260401", "close_qfq": 10.0, "volume_ratio": 1.0},
        {"trade_date": "20260402", "close_qfq": 10.2, "volume_ratio": 1.0},
        {"trade_date": "20260417", "close_qfq": 10.5, "volume_ratio": 1.6},
    ]

    result = compute_signal_flags_for_stock(rows, target_date="20260417")

    assert result["buy_volume_breakout_20d"] is True


def test_classify_resonance_level() -> None:
    assert classify_resonance_level(2) == "normal"
    assert classify_resonance_level(3) == "strong"
    assert classify_resonance_level(4) == "very_strong"
    assert classify_resonance_level(1) is None
```

- [ ] **Step 2: Run the new signal tests to verify they fail**

Run:

```bash
cd /home/james/projects/freedom/backend && pytest tests/signals/test_daily_stock_signals.py -v
```

Expected: FAIL with `ModuleNotFoundError` or missing function errors.

- [ ] **Step 3: Implement the minimal core helpers**

Create the module with focused pure functions:

```python
from __future__ import annotations

from collections import defaultdict
from typing import Any


BUY_SIGNAL_TYPES = (
    "buy_macd_kdj_double_cross",
    "buy_ma_bullish_formation",
    "buy_volume_breakout_20d",
    "buy_rsi_rebound",
)

SELL_SIGNAL_TYPES = (
    "sell_macd_kdj_double_cross",
    "sell_ma_bearish_formation",
    "sell_volume_breakdown_20d",
    "sell_rsi_fall",
)


def classify_resonance_level(signal_count: int) -> str | None:
    if signal_count >= 4:
        return "very_strong"
    if signal_count == 3:
        return "strong"
    if signal_count == 2:
        return "normal"
    return None


def compute_signal_flags_for_stock(rows: list[dict[str, Any]], *, target_date: str) -> dict[str, bool]:
    by_date = {str(row["trade_date"]): row for row in rows}
    dates = sorted(by_date)
    idx = dates.index(target_date)
    if idx == 0:
        return {name: False for name in (*BUY_SIGNAL_TYPES, *SELL_SIGNAL_TYPES)}

    prev_row = by_date[dates[idx - 1]]
    row = by_date[target_date]
    prior_window = [by_date[d] for d in dates[max(0, idx - 20):idx]]

    buy_cross = row["macd"] > row["macd_signal"] and prev_row["macd"] <= prev_row["macd_signal"]
    buy_kdj = row["kdj_k"] > row["kdj_d"] and prev_row["kdj_k"] <= prev_row["kdj_d"]
    sell_cross = row["macd"] < row["macd_signal"] and prev_row["macd"] >= prev_row["macd_signal"]
    sell_kdj = row["kdj_k"] < row["kdj_d"] and prev_row["kdj_k"] >= prev_row["kdj_d"]
    prior_high = max((float(item["close_qfq"]) for item in prior_window), default=float("-inf"))
    prior_low = min((float(item["close_qfq"]) for item in prior_window), default=float("inf"))

    return {
        "buy_macd_kdj_double_cross": buy_cross and buy_kdj,
        "buy_ma_bullish_formation": row["ma5"] > row["ma10"] > row["ma20"] > row["ma60"] and not (prev_row["ma5"] > prev_row["ma10"] > prev_row["ma20"] > prev_row["ma60"]),
        "buy_volume_breakout_20d": bool(prior_window) and row["close_qfq"] > prior_high and row["volume_ratio"] > 1.5,
        "buy_rsi_rebound": row["rsi6"] > row["rsi12"] and prev_row["rsi6"] <= prev_row["rsi12"] and prev_row["rsi6"] < 30,
        "sell_macd_kdj_double_cross": sell_cross and sell_kdj,
        "sell_ma_bearish_formation": row["ma5"] < row["ma10"] < row["ma20"] < row["ma60"] and not (prev_row["ma5"] < prev_row["ma10"] < prev_row["ma20"] < prev_row["ma60"]),
        "sell_volume_breakdown_20d": bool(prior_window) and row["close_qfq"] < prior_low and row["volume_ratio"] > 1.5,
        "sell_rsi_fall": row["rsi6"] < row["rsi12"] and prev_row["rsi6"] >= prev_row["rsi12"] and prev_row["rsi6"] > 70,
    }
```

- [ ] **Step 4: Expand the module to support grouped output construction**

Add focused builders for:
- stock-level enriched signal rows
- grouped signal documents
- grouped resonance documents

Use a shape like:

```python
def build_signal_documents(*, trade_date: str, stock_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ...


def build_resonance_documents(*, trade_date: str, stock_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ...
```

Each stock row should include only minimal signal-specific metrics.

- [ ] **Step 5: Re-run the signal tests**

Run:

```bash
cd /home/james/projects/freedom/backend && pytest tests/signals/test_daily_stock_signals.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit the core signal module**

```bash
cd /home/james/projects/freedom && git add backend/app/signals/daily_stock_signals.py backend/tests/signals/test_daily_stock_signals.py && git commit -m "feat: add daily stock signal computation core"
```

### Task 2: Add Mongo persistence helpers for signals and resonance

**Files:**
- Create: `backend/app/data/mongo_daily_stock_signals.py`
- Test: `backend/tests/services/test_daily_stock_signals_service.py`

- [ ] **Step 1: Write failing persistence tests for index and upsert behavior**

```python
from app.data.mongo_daily_stock_signals import upsert_daily_stock_signals, upsert_daily_stock_signal_resonance


def test_upsert_daily_stock_signals_returns_written_count(monkeypatch) -> None:
    class FakeCollection:
        def bulk_write(self, ops, ordered=False):
            self.ops = ops

    fake = FakeCollection()
    monkeypatch.setattr("app.data.mongo_daily_stock_signals.get_collection", lambda name: fake)
    monkeypatch.setattr("app.data.mongo_daily_stock_signals.ensure_daily_stock_signal_indexes", lambda: None)

    count = upsert_daily_stock_signals([
        {"trade_date": "20260417", "signal_type": "buy_macd_kdj_double_cross", "signal_side": "buy", "count": 0, "stocks": []}
    ])

    assert count == 1


def test_upsert_resonance_returns_zero_for_empty_input() -> None:
    assert upsert_daily_stock_signal_resonance([]) == 0
```

- [ ] **Step 2: Run the persistence tests and verify failure**

Run:

```bash
cd /home/james/projects/freedom/backend && pytest tests/services/test_daily_stock_signals_service.py -v
```

Expected: FAIL because the module does not exist.

- [ ] **Step 3: Implement the Mongo module using existing project patterns**

Follow `mongo_strategy_signal.py` style:

```python
from __future__ import annotations

import datetime as dt
from typing import Any

from pymongo import ASCENDING, DESCENDING, UpdateOne

from app.data.mongo import get_collection


def ensure_daily_stock_signal_indexes() -> None:
    get_collection("daily_stock_signals").create_index(
        [("trade_date", ASCENDING), ("signal_type", ASCENDING)],
        unique=True,
        name="idx_daily_stock_signals_unique",
    )
    get_collection("daily_stock_signals").create_index(
        [("trade_date", DESCENDING), ("signal_side", ASCENDING)],
        name="idx_daily_stock_signals_trade_side",
    )
    get_collection("daily_stock_signal_resonance").create_index(
        [("trade_date", ASCENDING), ("signal_side", ASCENDING), ("resonance_level", ASCENDING)],
        unique=True,
        name="idx_daily_stock_signal_resonance_unique",
    )


def upsert_daily_stock_signals(records: list[dict[str, Any]]) -> int:
    ...  # bulk_write(UpdateOne(..., upsert=True))


def upsert_daily_stock_signal_resonance(records: list[dict[str, Any]]) -> int:
    ...


def list_daily_stock_signal_dates(limit: int = 365) -> list[str]:
    ...


def get_signal_group(trade_date: str, signal_type: str) -> dict[str, Any] | None:
    ...


def list_signal_groups_for_date(trade_date: str, signal_side: str | None = None) -> list[dict[str, Any]]:
    ...


def list_resonance_groups_for_date(trade_date: str, signal_side: str | None = None) -> list[dict[str, Any]]:
    ...
```

- [ ] **Step 4: Re-run the persistence tests**

Run:

```bash
cd /home/james/projects/freedom/backend && pytest tests/services/test_daily_stock_signals_service.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit the Mongo persistence helpers**

```bash
cd /home/james/projects/freedom && git add backend/app/data/mongo_daily_stock_signals.py backend/tests/services/test_daily_stock_signals_service.py && git commit -m "feat: add daily stock signal mongo persistence"
```

### Task 3: Add the service layer and new API routes

**Files:**
- Create: `backend/app/services/daily_stock_signals_service.py`
- Create: `backend/app/api/routes/daily_stock_signals.py`
- Modify: `backend/app/api/routes/__init__.py`
- Modify: `backend/app/api/routers.py`
- Test: `backend/tests/api/test_daily_stock_signals_api.py`

- [ ] **Step 1: Write failing API tests for dates, overview, and by-type**

```python
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.daily_stock_signals import router as daily_stock_signals_router


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(daily_stock_signals_router, prefix="/api")
    return TestClient(app, raise_server_exceptions=False)


def test_get_dates_returns_items(monkeypatch) -> None:
    monkeypatch.setattr("app.api.routes.daily_stock_signals.list_daily_stock_signal_dates", lambda limit=365: ["20260417"])
    response = _client().get("/api/daily-stock-signals/dates")
    assert response.status_code == 200
    assert response.json() == {"items": ["20260417"], "total": 1}


def test_overview_defaults_to_latest_date(monkeypatch) -> None:
    monkeypatch.setattr("app.api.routes.daily_stock_signals.get_daily_stock_signals_overview", lambda trade_date=None, top_n=50: {"trade_date": "20260417", "buy_signals": [], "sell_signals": [], "buy_resonance": [], "sell_resonance": []})
    response = _client().get("/api/daily-stock-signals/overview")
    assert response.status_code == 200
    assert response.json()["trade_date"] == "20260417"
```

- [ ] **Step 2: Run the API tests to verify failure**

Run:

```bash
cd /home/james/projects/freedom/backend && pytest tests/api/test_daily_stock_signals_api.py -v
```

Expected: FAIL with missing route module errors.

- [ ] **Step 3: Implement the service layer**

Add service functions that keep API handlers thin:

```python
from app.data.mongo_daily_stock_signals import (
    get_signal_group,
    list_daily_stock_signal_dates,
    list_resonance_groups_for_date,
    list_signal_groups_for_date,
)


def get_daily_stock_signals_overview(*, trade_date: str | None = None, top_n: int = 50) -> dict[str, object]:
    ...


def get_daily_stock_signal_by_type(*, trade_date: str, signal_type: str) -> dict[str, object] | None:
    ...
```

The overview function should:
- default to the latest stored date when `trade_date` is omitted
- split results into `buy_signals`, `sell_signals`, `buy_resonance`, `sell_resonance`
- truncate each group’s `stocks` list to `top_n`

- [ ] **Step 4: Implement the FastAPI route module and router registration**

Follow the style of `strategy_signals.py`:

```python
from fastapi import APIRouter, HTTPException, Query

from app.services.daily_stock_signals_service import (
    get_daily_stock_signal_by_type,
    get_daily_stock_signals_overview,
    list_available_daily_stock_signal_dates,
)

router = APIRouter()


@router.get("/daily-stock-signals/dates")
def list_dates(limit: int = Query(default=365, ge=1, le=2000)) -> dict[str, object]:
    items = list_available_daily_stock_signal_dates(limit=limit)
    return {"items": items, "total": len(items)}
```

Then export and include the router in the main API router with auth dependency.

- [ ] **Step 5: Run API tests**

Run:

```bash
cd /home/james/projects/freedom/backend && pytest tests/api/test_daily_stock_signals_api.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit the API layer**

```bash
cd /home/james/projects/freedom && git add backend/app/services/daily_stock_signals_service.py backend/app/api/routes/daily_stock_signals.py backend/app/api/routes/__init__.py backend/app/api/routers.py backend/tests/api/test_daily_stock_signals_api.py && git commit -m "feat: add daily stock signals api"
```

### Task 4: Add the daily generation script with single-date, range, and backfill modes

**Files:**
- Create: `backend/scripts/daily/generate_daily_stock_signals.py`
- Test: `backend/tests/scripts/test_generate_daily_stock_signals.py`

- [ ] **Step 1: Write failing script tests for date resolution and trading-day filtering**

```python
from backend.scripts.daily.generate_daily_stock_signals import normalize_date, resolve_dates


def test_normalize_date_accepts_yyyymmdd_and_yyyy_mm_dd() -> None:
    assert normalize_date("20260417") == "20260417"
    assert normalize_date("2026-04-17") == "20260417"


def test_resolve_dates_last_days_maps_to_trading_days(monkeypatch) -> None:
    class Args:
        trade_date = None
        start_date = None
        end_date = None
        last_days = 365

    monkeypatch.setattr("backend.scripts.daily.generate_daily_stock_signals.get_trading_days", lambda start, end: ["20260416", "20260417"])

    assert resolve_dates(Args()) == ["20260416", "20260417"]
```

- [ ] **Step 2: Run the script tests and verify failure**

Run:

```bash
cd /home/james/projects/freedom/backend && pytest tests/scripts/test_generate_daily_stock_signals.py -v
```

Expected: FAIL due to missing script module.

- [ ] **Step 3: Implement the CLI shell around the core module**

Follow `calculate_signal.py` and `pull_daily_history.py` patterns:

```python
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate daily stock signals")
    parser.add_argument("--trade-date", type=str, default=None)
    parser.add_argument("--start-date", type=str, default=None)
    parser.add_argument("--end-date", type=str, default=None)
    parser.add_argument("--last-days", type=int, default=None)
    return parser.parse_args()


def resolve_dates(args: argparse.Namespace) -> list[str]:
    ...  # natural-day range -> trading days only


def main() -> None:
    args = parse_args()
    dates = resolve_dates(args)
    for trade_date in dates:
        signal_docs, resonance_docs = generate_daily_stock_signal_docs(trade_date=trade_date)
        upsert_daily_stock_signals(signal_docs)
        upsert_daily_stock_signal_resonance(resonance_docs)
```

- [ ] **Step 4: Add a bulk range path for one-year backfill**

Extend the core module or script to support buffered interval reads instead of full-market rereads per target date.

Implement a helper like:

```python
def generate_daily_stock_signal_docs_for_range(*, start_date: str, end_date: str, lookback_days: int = 60) -> tuple[list[dict], list[dict]]:
    ...
```

The helper should:
- load the requested date range plus lookback buffer once
- group by `ts_code`
- compute signal flags by date per stock
- emit only requested target trade dates

- [ ] **Step 5: Run script tests**

Run:

```bash
cd /home/james/projects/freedom/backend && pytest tests/scripts/test_generate_daily_stock_signals.py -v
```

Expected: PASS.

- [ ] **Step 6: Manually smoke-test the script for one day**

Run:

```bash
cd /home/james/projects/freedom/backend && python scripts/daily/generate_daily_stock_signals.py --trade-date 20260417
```

Expected: logs show 8 signal docs + 6 resonance docs upserted for `20260417`.

- [ ] **Step 7: Commit the script**

```bash
cd /home/james/projects/freedom && git add backend/scripts/daily/generate_daily_stock_signals.py backend/tests/scripts/test_generate_daily_stock_signals.py backend/app/signals/daily_stock_signals.py && git commit -m "feat: add daily stock signal generation script"
```

### Task 5: Register the daily task in Airflow and cover DAG behavior with tests

**Files:**
- Modify: `backend/app/airflow_sync/daily_sync_registry.py`
- Modify: `backend/airflow/dags/freedom_market_data_daily.py`
- Modify: `backend/tests/airflow/test_daily_sync_registry.py`
- Modify: `backend/tests/airflow/test_freedom_market_data_daily.py`

- [ ] **Step 1: Write or extend failing Airflow tests**

Add expectations like:

```python
def test_registry_contains_signals_and_screeners_group() -> None:
    groups = {task.group for task in DAILY_SYNC_TASKS}
    assert "signals_and_screeners" in groups
    assert get_daily_sync_task("generate_daily_stock_signals").script_path == "backend/scripts/daily/generate_daily_stock_signals.py"


def test_market_data_dag_wires_signals_group_after_factor_and_flow() -> None:
    dag = build_or_import_market_data_dag()
    task = dag.get_task("signals_and_screeners.generate_daily_stock_signals")
    upstream = set(task.upstream_task_ids)
    assert "market_core" in upstream or "market_core.pull_daily_history" in upstream
```

- [ ] **Step 2: Run the Airflow tests and verify failure**

Run:

```bash
cd /home/james/projects/freedom/backend && pytest tests/airflow/test_daily_sync_registry.py tests/airflow/test_freedom_market_data_daily.py -v
```

Expected: FAIL because the new task/group is not registered yet.

- [ ] **Step 3: Add the registry task**

Add a new `DailySyncTask` entry:

```python
DailySyncTask(
    task_id="generate_daily_stock_signals",
    group="signals_and_screeners",
    script_path="backend/scripts/daily/generate_daily_stock_signals.py",
    retries=2,
    retry_delay_minutes=10,
)
```

- [ ] **Step 4: Add the new task group and dependencies in the DAG**

Update the group list to include `signals_and_screeners`, then wire:

```python
precheck_trade_day >> groups["market_core"]
groups["market_core"] >> groups["factor_and_flow"]
groups["market_core"] >> groups["signals_and_screeners"]
groups["factor_and_flow"] >> groups["signals_and_screeners"]
groups["signals_and_screeners"] >> finalize_run
```

- [ ] **Step 5: Re-run the Airflow tests**

Run:

```bash
cd /home/james/projects/freedom/backend && pytest tests/airflow/test_daily_sync_registry.py tests/airflow/test_freedom_market_data_daily.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit the Airflow integration**

```bash
cd /home/james/projects/freedom && git add backend/app/airflow_sync/daily_sync_registry.py backend/airflow/dags/freedom_market_data_daily.py backend/tests/airflow/test_daily_sync_registry.py backend/tests/airflow/test_freedom_market_data_daily.py && git commit -m "feat: wire daily stock signals into airflow"
```

### Task 6: Build the new frontend page and connect it to the new API

**Files:**
- Create: `frontend/pages/daily-stock-signals.js`
- Modify: `frontend/styles/globals.css` (or the existing page stylesheet if daily-signals uses a different CSS source)

- [ ] **Step 1: Build the page from the existing daily-signals page pattern**

Start from the calendar/date-loading pattern in `frontend/pages/daily-signals.js`, but point it to the new endpoints:

```javascript
const loadDates = async () => {
  const res = await apiFetch(`/daily-stock-signals/dates`);
  ...
};

const loadOverview = async (tradeDate) => {
  const params = new URLSearchParams();
  if (tradeDate) params.set("trade_date", tradeDate);
  const res = await apiFetch(`/daily-stock-signals/overview?${params.toString()}`);
  ...
};
```

Render:
- summary cards
- buy signal cards
- sell signal cards
- buy resonance buckets
- sell resonance buckets

- [ ] **Step 2: Add minimal styling for the new grouped layout**

Add card/grid styles only as needed, reusing existing page conventions.

Example class targets:

```css
.signal-summary-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; }
.signal-section-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 20px; }
.signal-card { border-radius: 16px; padding: 16px; background: #0f172a; }
.resonance-bucket { margin-top: 12px; }
```

- [ ] **Step 3: Run frontend lint/build checks**

Run:

```bash
cd /home/james/projects/freedom/frontend && npm run lint && npm run build
```

Expected: PASS.

- [ ] **Step 4: Commit the frontend page**

```bash
cd /home/james/projects/freedom && git add frontend/pages/daily-stock-signals.js frontend/styles/globals.css && git commit -m "feat: add daily stock signals page"
```

### Task 7: Execute one-year backfill and verify end-to-end behavior

**Files:**
- No new code required unless a verification gap appears.

- [ ] **Step 1: Run the backend test suite for all touched areas**

Run:

```bash
cd /home/james/projects/freedom/backend && pytest tests/signals/test_daily_stock_signals.py tests/services/test_daily_stock_signals_service.py tests/api/test_daily_stock_signals_api.py tests/scripts/test_generate_daily_stock_signals.py tests/airflow/test_daily_sync_registry.py tests/airflow/test_freedom_market_data_daily.py -v
```

Expected: PASS.

- [ ] **Step 2: Run the one-year backfill**

Run:

```bash
cd /home/james/projects/freedom/backend && python scripts/daily/generate_daily_stock_signals.py --last-days 365
```

Expected: logs show processing of all trading days in the last 365 natural days with idempotent upserts.

- [ ] **Step 3: Verify stored dates and a sample overview**

Run:

```bash
cd /home/james/projects/freedom/backend && python - <<'PY'
from app.data.mongo_daily_stock_signals import list_daily_stock_signal_dates
from app.services.daily_stock_signals_service import get_daily_stock_signals_overview

dates = list_daily_stock_signal_dates(limit=10)
print(dates[:5])
assert dates
overview = get_daily_stock_signals_overview(trade_date=dates[0], top_n=5)
print(overview["trade_date"], len(overview["buy_signals"]), len(overview["sell_signals"]))
PY
```

Expected: non-empty date list; overview contains 8 signal groups and 6 resonance groups.

- [ ] **Step 4: Verify the page manually**

Run backend/frontend locally, then open:

```text
http://localhost:3000/freedom/daily-stock-signals
```

Manual checks:
- latest date auto-loads
- switching dates refreshes content
- buy/sell/resonance sections render
- no crash on empty groups

- [ ] **Step 5: Commit any final verification-driven fixes**

```bash
cd /home/james/projects/freedom && git add . && git commit -m "feat: finalize daily stock signals rollout"
```

## Self-Review

### Spec coverage
- Core computation and the 8 signal rules: Task 1
- Mongo data model and empty-doc policy: Task 2
- API routes and top-50 overview limit: Task 3
- CLI modes and one-year backfill support: Task 4
- Airflow DAG integration: Task 5
- Frontend page: Task 6
- One-year backfill execution and verification: Task 7

### Placeholder scan
- No TBD/TODO placeholders remain.
- All tasks contain exact file paths, commands, and concrete implementation direction.

### Type consistency
- Route family consistently uses `daily-stock-signals`.
- Mongo collection names consistently use `daily_stock_signals` and `daily_stock_signal_resonance`.
- Script/task name consistently uses `generate_daily_stock_signals`.
