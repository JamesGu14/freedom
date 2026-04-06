# P1 Holder Data Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add first-pass local storage and sync scripts for shareholder count and top-10 holder datasets.

**Architecture:** Store `stk_holdernumber` in DuckDB for later analytical joins, and keep `top10_holders` plus `top10_floatholders` in Mongo to preserve full report-detail payloads with simple upsert semantics. Use full-market paginated sync windows instead of per-stock crawling.

**Tech Stack:** Python 3.12, TuShare API, DuckDB, MongoDB, pytest

---

### Task 1: Add failing tests for holder storage and sync helpers

**Files:**
- Create: `backend/tests/data/test_duckdb_shareholders.py`
- Create: `backend/tests/data/test_mongo_top10_holders.py`
- Create: `backend/tests/scripts/test_sync_holder_scripts.py`

### Task 2: Implement minimal persistence helpers

**Files:**
- Create: `backend/app/data/duckdb_shareholders.py`
- Create: `backend/app/data/mongo_top10_holders.py`

### Task 3: Extend TuShare client and sync scripts

**Files:**
- Modify: `backend/app/data/tushare_client.py`
- Create: `backend/scripts/daily/sync_holdernumber.py`
- Create: `backend/scripts/daily/sync_top10_holders.py`

### Task 4: Verify with targeted tests

**Files:**
- Test: `backend/tests/data/test_duckdb_shareholders.py`
- Test: `backend/tests/data/test_mongo_top10_holders.py`
- Test: `backend/tests/scripts/test_sync_holder_scripts.py`

### Task 5: Run real sync and validate storage

**Files:**
- Use: `backend/scripts/daily/sync_holdernumber.py`
- Use: `backend/scripts/daily/sync_top10_holders.py`
