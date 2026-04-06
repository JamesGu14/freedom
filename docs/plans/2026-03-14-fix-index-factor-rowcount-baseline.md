# Index Factor Rowcount Baseline Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Stop `index_factor_pro` from reporting false-positive rowcount anomalies when MongoDB row counts already match the local `idx_factor_pro` Parquet dataset for the same trade date.

**Architecture:** Extend the audit dataset registry so `index_factor_pro` can declare a rowcount reference source, then teach the audit runner and rowcount anomaly engine to prefer same-day reference counts over the rolling median when a reference exists. Keep the rolling median as a fallback and as reporting context.

**Tech Stack:** Python 3.11, audit registry/runner/engine modules, local Parquet via DuckDB, pytest.

---

### Task 1: Add failing tests for reference-aware rowcount anomalies

**Files:**
- Modify: `backend/tests/audit/test_engine.py`
- Modify: `backend/tests/audit/test_registry.py`
- Modify: `backend/tests/audit/test_runner.py`

**Step 1:** Add a failing engine test showing that a rowcount equal to a same-day reference count should not be flagged even if it is below the recent rolling median.
**Step 2:** Add a failing registry test showing that `index_factor_pro` declares a rowcount reference source.
**Step 3:** Add a failing runner test showing that `run_audit()` loads the reference counts and suppresses false-positive `index_factor_pro` anomalies.
**Step 4:** Run `pytest backend/tests/audit -q` and verify the new tests fail for the expected reason.

### Task 2: Implement reference-aware rowcount logic

**Files:**
- Modify: `backend/app/audit/models.py`
- Modify: `backend/app/audit/registry.py`
- Modify: `backend/app/audit/engine.py`
- Modify: `backend/scripts/audit/run_data_integrity_audit.py`

**Step 1:** Add optional rowcount reference metadata to `DatasetConfig`.
**Step 2:** Update `compute_rowcount_anomalies()` to prefer same-day reference counts when available and keep the rolling median as context.
**Step 3:** Update `run_audit()` so rowcount-based datasets can load reference counts and pass them into the engine.
**Step 4:** Re-run `pytest backend/tests/audit -q` and verify all tests pass.

### Task 3: Verify on real data

**Files:**
- No source changes required unless verification reveals a bug

**Step 1:** Run `python backend/scripts/audit/run_data_integrity_audit.py --datasets index_factor_pro --run-id verify_index_factor_pro_rowcount_reference`.
**Step 2:** Confirm that `missing_dates=0` remains true.
**Step 3:** Confirm that the false-positive `rowcount_anomalies` count drops to match only genuine gaps, or to zero if none remain.

---

## Execution Status

- Tests passed: `pytest backend/tests/audit -q`
- Audit rule updated so `index_factor_pro` prefers same-day local Parquet row counts over the rolling median when a reference exists.
- Real-data verification exposed that `2025-07-11` onward anomalies were genuine MongoDB lag versus local Parquet, not rule noise.
- Local Parquet backfill report: `logs/data_repair/p0_index_factor_pro_rowcount_local_20260314_095702/summary.json`
- Final verification report: `logs/data_audit/verify_index_factor_pro_after_rowcount_local_repair/summary.json`
- Final state:
  - `missing_dates=0`
  - `coverage_anomalies=0`
  - `rowcount_anomalies=0`
