# P1 Dividend Data Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ingest TuShare `dividend` data into the existing `dividend_history` MongoDB collection so dividend APIs have real local source data.

**Architecture:** Store the raw TuShare dividend payload directly in `dividend_history`, keyed by `ts_code + end_date + ann_date + div_proc`. Preserve all source fields and leave advanced screening metrics as a follow-up enrichment step.

**Tech Stack:** Python 3.11, MongoDB, TuShare Pro, pytest

---

### Task 1: Add failing persistence tests

**Files:**
- Create: `backend/tests/data/test_mongo_dividend_history.py`

### Task 2: Add Mongo storage module

**Files:**
- Create: `backend/app/data/mongo_dividend_history.py`
- Test: `backend/tests/data/test_mongo_dividend_history.py`

### Task 3: Add failing sync-script tests

**Files:**
- Create: `backend/tests/scripts/test_sync_dividend_script.py`

### Task 4: Extend TuShare client and sync script

**Files:**
- Modify: `backend/app/data/tushare_client.py`
- Create: `backend/scripts/daily/sync_dividend.py`
- Test: `backend/tests/scripts/test_sync_dividend_script.py`

### Task 5: Run targeted tests and real sync

**Files:**
- Test: `backend/tests/data/test_mongo_dividend_history.py`
- Test: `backend/tests/scripts/test_sync_dividend_script.py`

### Task 6: Update docs and follow-up notes

**Files:**
- Modify: `docs/tushare_5000积分接口实现对照.md`
- Modify: `docs/plans/2026-03-15-p1-dividend-data-design.md`

### Result

- Real sync completed with:
  - `days=550`
  - `api_rows=43565`
  - `upserted=43174`
- Current local collection:
  - `dividend_history=43174`
  - `ann_date` range `20240104 ~ 20260314`
  - `end_date` range `20230930 ~ 20260116`
