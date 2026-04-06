# Airflow Weekly Data Integrity Audit Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a standalone weekly Airflow DAG that runs the local data integrity audit and persists each audit summary to MongoDB.

**Architecture:** Reuse `backend/scripts/audit/run_data_integrity_audit.py` through a small Python helper that executes the audit, converts the result into a stable Mongo document, and upserts it into a dedicated collection. Keep the DAG minimal: one `PythonOperator`, one schedule, no coupling to `daily.sh`.

**Tech Stack:** Python 3.11, existing audit package, Airflow DAG file under `backend/airflow/dags`, MongoDB via `pymongo`, pytest.

---

### Task 1: Add the audit-run Mongo model helper

**Files:**
- Create: `backend/app/data/mongo_data_integrity_audit.py`
- Test: `backend/tests/data/test_mongo_data_integrity_audit.py`

**Step 1:** Write a failing test for upserting an audit-run document and ensuring indexes.
**Step 2:** Run `pytest backend/tests/data/test_mongo_data_integrity_audit.py -v`.
**Step 3:** Implement the minimal collection helper and index creation.
**Step 4:** Re-run the test and verify it passes.

### Task 2: Add an Airflow-facing audit runner helper

**Files:**
- Create: `backend/app/audit/airflow_runner.py`
- Test: `backend/tests/audit/test_airflow_runner.py`

**Step 1:** Write a failing test for converting an `AuditRunResult` into a Mongo-ready payload with status counts and dataset summaries.
**Step 2:** Run `pytest backend/tests/audit/test_airflow_runner.py -v`.
**Step 3:** Implement the minimal payload builder and persistence wrapper.
**Step 4:** Re-run the test and verify it passes.

### Task 3: Add the weekly Airflow DAG

**Files:**
- Create: `backend/airflow/dags/freedom_data_integrity_weekly.py`

**Step 1:** Implement a minimal DAG with:
- `dag_id=freedom_data_integrity_weekly`
- schedule `0 6 * * 6`
- timezone `Asia/Shanghai`
- one `PythonOperator`
**Step 2:** Wire the task to call the helper from Task 2.
**Step 3:** Keep output in `logs/data_audit/<run_id>/` and persist Mongo summary in the same run.

### Task 4: Document the Airflow integration

**Files:**
- Modify: `README.md`
- Modify: `openspec/changes/add-data-integrity-audit/design.md`

**Step 1:** Add concise notes that the audit now supports weekly Airflow scheduling.
**Step 2:** Document the Mongo collection name and what gets stored.

### Task 5: Verify end-to-end behavior

**Files:**
- Modify as needed: `backend/app/audit/airflow_runner.py`
- Modify as needed: `backend/app/data/mongo_data_integrity_audit.py`
- Modify as needed: `backend/airflow/dags/freedom_data_integrity_weekly.py`

**Step 1:** Run:
`pytest backend/tests/data/test_mongo_data_integrity_audit.py backend/tests/audit/test_airflow_runner.py -v`
**Step 2:** Run the full audit test suite:
`pytest backend/tests/audit -q`
**Step 3:** Execute the Airflow callable locally if the environment allows it.
**Step 4:** Verify:
- report files exist under `logs/data_audit/<run_id>/`
- Mongo contains one `data_integrity_audit_runs` document
