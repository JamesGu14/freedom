# Data Integrity Audit Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a local offline audit tool that scans configured daily datasets from MongoDB, DuckDB, and Parquet, then writes Markdown, CSV, and JSON integrity reports under `logs/data_audit/<run_id>/`.

**Architecture:** Put reusable audit logic in a new `backend/app/audit/` package, with a thin CLI runner in `backend/scripts/audit/run_data_integrity_audit.py`. Use a dataset registry to describe each dataset's storage backend and audit mode, then run date-gap, coverage, and row-count anomaly checks through shared helpers.

**Tech Stack:** Python 3.11, pathlib, dataclasses, csv/json output, existing MongoDB access helpers, DuckDB read connection manager, unittest/pytest-compatible backend tests.

---

### Task 1: Create the audit registry

**Files:**
- Create: `backend/app/audit/__init__.py`
- Create: `backend/app/audit/registry.py`
- Test: `backend/tests/audit/test_registry.py`

**Step 1:** Write a failing test asserting the registry includes the first-scope datasets and fixed rules.
**Step 2:** Run `pytest backend/tests/audit/test_registry.py -v` and verify the failure is due to missing registry code.
**Step 3:** Implement the minimal registry dataclass and dataset declarations.
**Step 4:** Re-run `pytest backend/tests/audit/test_registry.py -v` and verify it passes.

### Task 2: Add date-gap audit primitives

**Files:**
- Create: `backend/app/audit/models.py`
- Create: `backend/app/audit/engine.py`
- Test: `backend/tests/audit/test_engine.py`

**Step 1:** Write a failing test for computing missing trade dates from local min/max and calendar dates.
**Step 2:** Run `pytest backend/tests/audit/test_engine.py -v` and verify the failure is expected.
**Step 3:** Implement the minimal date-gap function and result model.
**Step 4:** Re-run `pytest backend/tests/audit/test_engine.py -v` and verify it passes.

### Task 3: Add coverage and row-count anomaly primitives

**Files:**
- Modify: `backend/app/audit/models.py`
- Modify: `backend/app/audit/engine.py`
- Test: `backend/tests/audit/test_engine.py`

**Step 1:** Add failing tests for coverage ratio classification and row-count anomaly classification using the agreed thresholds.
**Step 2:** Run `pytest backend/tests/audit/test_engine.py -v`.
**Step 3:** Implement the minimal threshold logic.
**Step 4:** Re-run `pytest backend/tests/audit/test_engine.py -v` and verify all tests pass.

### Task 4: Add report builders

**Files:**
- Create: `backend/app/audit/report_builder.py`
- Test: `backend/tests/audit/test_report_builder.py`

**Step 1:** Write a failing test asserting the report builder creates `summary.md`, CSV details, and `summary.json` under `logs/data_audit/<run_id>/`.
**Step 2:** Run `pytest backend/tests/audit/test_report_builder.py -v`.
**Step 3:** Implement the minimal report output helpers.
**Step 4:** Re-run `pytest backend/tests/audit/test_report_builder.py -v`.

### Task 5: Wire a runnable CLI

**Files:**
- Create: `backend/scripts/audit/run_data_integrity_audit.py`
- Test: `backend/tests/audit/test_runner.py`

**Step 1:** Write a failing test for CLI argument parsing and fixed output directory behavior.
**Step 2:** Run `pytest backend/tests/audit/test_runner.py -v`.
**Step 3:** Implement the minimal runner that loads the registry, creates a run id, and writes placeholder-real outputs through the report builder.
**Step 4:** Re-run `pytest backend/tests/audit/test_runner.py -v`.

### Task 6: Add backend-specific adapters

**Files:**
- Modify: `backend/app/audit/engine.py`
- Possibly Create: `backend/app/audit/adapters.py`
- Test: `backend/tests/audit/test_adapters.py`

**Step 1:** Write failing tests for extracting dataset date ranges and daily counts from mocked Mongo/DuckDB/Parquet readers.
**Step 2:** Run `pytest backend/tests/audit/test_adapters.py -v`.
**Step 3:** Implement the minimal adapter helpers around existing data access functions.
**Step 4:** Re-run `pytest backend/tests/audit/test_adapters.py -v`.

### Task 7: Run targeted verification

**Files:**
- Modify: `backend/app/audit/*.py`
- Modify: `backend/scripts/audit/run_data_integrity_audit.py`

**Step 1:** Run the focused audit test suite.
**Step 2:** Run `python backend/scripts/audit/run_data_integrity_audit.py --help`.
**Step 3:** Run one local smoke invocation if the environment allows it.
**Step 4:** Fix any failing tests or output-path issues.

### Task 8: Document usage

**Files:**
- Modify: `README.md` or another relevant doc if appropriate
- Keep: `openspec/changes/add-data-integrity-audit/*`

**Step 1:** Add concise usage notes for running the audit and reading the output.
**Step 2:** Re-run the targeted tests to ensure documentation edits did not affect code paths.
