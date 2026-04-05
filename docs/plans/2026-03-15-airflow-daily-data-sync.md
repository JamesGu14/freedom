# Airflow Daily Data Sync Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move all current daily-updated Freedom data sync jobs into `ai-personal-os` shared Airflow while keeping execution independent from the FastAPI service and pinned to the host machine as the only TuShare execution surface.

**Architecture:** Shared Airflow owns scheduling, retries, and task grouping. Each Airflow task invokes a small host-side runner that activates the existing Freedom environment and executes exactly one sync script. `daily.sh` is not reused as the execution unit; instead, the DAG is decomposed into observable dataset-level tasks with explicit dependencies.

**Tech Stack:** Airflow, Python 3.11, existing `backend/scripts/daily/*` sync scripts, host shell runner, shared Airflow deployment in `ai-personal-os`.

---

### Task 1: Add the design-backed dataset registry for the DAG

**Files:**
- Create: `backend/airflow/daily_sync_registry.py`
- Test: `backend/tests/airflow/test_daily_sync_registry.py`

**Step 1:** Write a failing test for registry entries, command rendering, and grouping.

**Step 2:** Run `pytest backend/tests/airflow/test_daily_sync_registry.py -v` and confirm failure.

**Step 3:** Implement a minimal registry that declares:
- task id
- group
- command
- retries
- retry delay
- critical flag

**Step 4:** Run the test again and confirm pass.

### Task 2: Add a host execution helper

**Files:**
- Create: `backend/airflow/host_job_runner.py`
- Test: `backend/tests/airflow/test_host_job_runner.py`

**Step 1:** Write a failing test that validates:
- conda activation command construction
- project-root working directory
- log path rendering
- date argument injection

**Step 2:** Run `pytest backend/tests/airflow/test_host_job_runner.py -v` and confirm failure.

**Step 3:** Implement the minimal helper to build one host command per dataset task.

**Step 4:** Run the test again and confirm pass.

### Task 3: Add trade-day precheck helper

**Files:**
- Create: `backend/airflow/trade_day_guard.py`
- Test: `backend/tests/airflow/test_trade_day_guard.py`

**Step 1:** Write a failing test for:
- trading-day returns true
- non-trading-day returns false
- date normalization

**Step 2:** Run `pytest backend/tests/airflow/test_trade_day_guard.py -v` and confirm failure.

**Step 3:** Implement the helper using existing local Mongo trade-calendar access.

**Step 4:** Run the test again and confirm pass.

### Task 4: Create the shared Airflow DAG in the Freedom repo

**Files:**
- Create: `backend/airflow/dags/freedom_market_data_daily.py`
- Test: `backend/tests/airflow/test_freedom_market_data_daily.py`

**Step 1:** Write a failing DAG-structure test that validates:
- DAG id
- `20:30 Asia/Shanghai` schedule
- TaskGroup layout
- critical task presence

**Step 2:** Run `pytest backend/tests/airflow/test_freedom_market_data_daily.py -v` and confirm failure.

**Step 3:** Implement the DAG using:
- `precheck_trade_day`
- `market_core`
- `factor_and_flow`
- `financials_and_corporate`
- `holders_and_margin`
- `index_and_industry`
- `finalize_run`

**Step 4:** Run the DAG test again and confirm pass.

### Task 5: Deploy the DAG to `ai-personal-os` shared Airflow

**Files:**
- Create: `/home/james/projects/ai-personal-os/infra/shared-infra/airflow/dags/freedom_market_data_daily.py`
- Modify if needed: `/home/james/projects/ai-personal-os/infra/shared-infra/docker-compose.yml`

**Step 1:** Copy the validated DAG into the shared Airflow DAG directory.

**Step 2:** If imports require it, add the smallest environment/config update needed for the scheduler to load the DAG.

**Step 3:** Run a DAG parse check such as:
`python -m py_compile /home/james/projects/ai-personal-os/infra/shared-infra/airflow/dags/freedom_market_data_daily.py`

**Step 4:** Restart or refresh shared Airflow services if required and verify the DAG is listed.

### Task 6: Add the host runner entrypoint used by Airflow

**Files:**
- Create: `scripts/run_freedom_sync_job.sh`
- Test: `backend/tests/airflow/test_host_job_runner.py`

**Step 1:** Write a failing test for the exact shell entrypoint format if not already covered.

**Step 2:** Run the targeted test and confirm failure.

**Step 3:** Implement the shell wrapper to:
- activate conda `freedom`
- set `PYTHONPATH`
- `cd /home/james/projects/freedom`
- run one sync command
- tee output to a task-specific log file

**Step 4:** Run the targeted test again and confirm pass.

### Task 7: Validate one real task from each TaskGroup

**Files:**
- Validate existing sync scripts only

**Step 1:** Run one real task from each group for a narrow recent date window.

Suggested commands:
- `pull_daily_history.py`
- `sync_stk_factor_pro.py`
- `sync_financial_reports.py --dataset income`
- `sync_holdernumber.py`
- `sync_index_daily.py`

**Step 2:** Confirm:
- exit status `0`
- log files written
- expected local stores updated

### Task 8: Update docs and migration notes

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `docs/tushare_5000积分接口实现对照.md`
- Modify: `docs/plans/2026-03-15-airflow-daily-data-sync-design.md`

**Step 1:** Document:
- daily schedule `20:30 Asia/Shanghai`
- shared Airflow ownership
- host-only TuShare execution surface
- explicit non-use of `daily.sh` for Airflow execution

**Step 2:** Run targeted doc sanity checks or `rg` checks to ensure no contradictory wording remains.

### Task 9: Final verification

**Files:**
- Modify as needed: all touched files above

**Step 1:** Run targeted tests:
- `pytest backend/tests/airflow -q`

**Step 2:** Run DAG parse validation:
- `python -m py_compile backend/airflow/dags/freedom_market_data_daily.py`
- `python -m py_compile /home/james/projects/ai-personal-os/infra/shared-infra/airflow/dags/freedom_market_data_daily.py`

**Step 3:** Verify the DAG appears in shared Airflow and is unpaused or intentionally paused according to deployment policy.
