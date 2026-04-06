# Async Airflow Trigger For Freedom Data Audit Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Let the shared `ai-personal-os` Airflow trigger Freedom's weekly data integrity audit asynchronously and monitor completion without holding a long HTTP request open.

**Architecture:** Add a small audit-run job service inside `freedom` that can create a run record, execute the existing audit in a background thread, and expose trigger/status APIs. Then deploy a thin DAG into `ai-personal-os` shared Airflow that calls Freedom over authenticated HTTP, polls run status, and fails fast if the run reports an error. Keep MongoDB as the source of truth for run status and summary.

**Tech Stack:** FastAPI, MongoDB, Python threading, urllib-based internal HTTP client, Apache Airflow 3.1.7, pytest.

---

### Task 1: Add audit run state persistence and service logic

**Files:**
- Modify: `backend/app/data/mongo_data_integrity_audit.py`
- Create: `backend/app/services/data_integrity_audit_job_service.py`
- Test: `backend/tests/services/test_data_integrity_audit_job_service.py`

**Step 1:** Write failing tests for creating a queued run, marking it running/succeeded/failed, and returning API-safe summaries.
**Step 2:** Run `pytest backend/tests/services/test_data_integrity_audit_job_service.py -v`.
**Step 3:** Implement the minimal Mongo helpers and in-process background execution service.
**Step 4:** Re-run the test and verify it passes.

### Task 2: Add async trigger/status APIs in Freedom

**Files:**
- Create: `backend/app/api/routes/internal_audits.py`
- Modify: `backend/app/api/routes/__init__.py`
- Modify: `backend/app/api/routers.py`
- Test: `backend/tests/api/test_internal_audits_api.py`

**Step 1:** Write failing API tests for:
- `POST /api/internal/audits/data-integrity/runs`
- `GET /api/internal/audits/data-integrity/runs/{run_id}`
- auth requirement and 404 behavior
**Step 2:** Run `pytest backend/tests/api/test_internal_audits_api.py -v`.
**Step 3:** Implement the minimal routes using the new service.
**Step 4:** Re-run the test and verify it passes.

### Task 3: Add the shared Airflow HTTP DAG in ai-personal-os

**Files:**
- Create: `/home/james/projects/ai-personal-os/infra/shared-infra/airflow/dags/freedom_data_integrity_weekly.py`
- Modify: `/home/james/projects/ai-personal-os/infra/shared-infra/docker-compose.yml`

**Step 1:** Add a DAG that:
- runs weekly at `0 6 * * 6`
- calls Freedom trigger API
- polls Freedom status API until success/failure/timeout
**Step 2:** Add any minimal environment/plumbing needed so the Airflow containers know Freedom base URL and API token.
**Step 3:** Keep DAG logic thin; do not reimplement audit logic in Airflow.

### Task 4: Document and verify deployment

**Files:**
- Modify: `README.md`
- Modify: `openspec/changes/add-data-integrity-audit/design.md`

**Step 1:** Document the async trigger model and Mongo persistence.
**Step 2:** Run focused tests:
- `pytest backend/tests/services/test_data_integrity_audit_job_service.py backend/tests/api/test_internal_audits_api.py -q`
- `pytest backend/tests/data/test_mongo_data_integrity_audit.py backend/tests/audit/test_airflow_runner.py backend/tests/audit -q`
**Step 3:** Run syntax/static checks:
- `python -m py_compile backend/app/services/data_integrity_audit_job_service.py`
- `python -m py_compile backend/app/api/routes/internal_audits.py`
- `python -m py_compile /home/james/projects/ai-personal-os/infra/shared-infra/airflow/dags/freedom_data_integrity_weekly.py`
**Step 4:** Deploy/restart shared Airflow services and verify the DAG is listed.
