# P1 Margin Data Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add TuShare `margin` and `margin_detail` ingestion so the platform can persist融资融券汇总与个股明细数据 locally.

**Architecture:** Store market-level `margin` in MongoDB with a unique `(trade_date, exchange_id)` key. Store stock-level `margin_detail` in DuckDB with explicit analytical columns and `raw_payload`, syncing both through paginated date-window scripts.

**Tech Stack:** Python 3.11, FastAPI data modules, MongoDB, DuckDB, TuShare Pro, pytest

---

### Task 1: Add failing persistence tests

**Files:**
- Create: `backend/tests/data/test_mongo_margin.py`
- Create: `backend/tests/data/test_duckdb_margin.py`

### Task 2: Add margin storage modules

**Files:**
- Create: `backend/app/data/mongo_margin.py`
- Create: `backend/app/data/duckdb_margin.py`
- Test: `backend/tests/data/test_mongo_margin.py`
- Test: `backend/tests/data/test_duckdb_margin.py`

### Task 3: Add failing sync-script tests

**Files:**
- Create: `backend/tests/scripts/test_sync_margin_scripts.py`

### Task 4: Extend TuShare client and sync scripts

**Files:**
- Modify: `backend/app/data/tushare_client.py`
- Create: `backend/scripts/daily/sync_margin.py`
- Create: `backend/scripts/daily/sync_margin_detail.py`
- Test: `backend/tests/scripts/test_sync_margin_scripts.py`

### Task 5: Run targeted tests and real sync

**Files:**
- Test: `backend/tests/data/test_mongo_margin.py`
- Test: `backend/tests/data/test_duckdb_margin.py`
- Test: `backend/tests/scripts/test_sync_margin_scripts.py`
