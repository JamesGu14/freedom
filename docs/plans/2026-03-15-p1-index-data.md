# P1 Index Data Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add TuShare `index_basic` and a 10-index-whitelist `index_daily` ingestion path for core benchmark and style index research.

**Architecture:** Store both datasets in MongoDB. `index_basic` will sync the full supported dictionary, while `index_daily` will sync only a curated whitelist of 10 core index codes, keyed by `ts_code + trade_date`, to avoid prematurely building a very large index universe.

**Tech Stack:** Python 3.11, MongoDB, TuShare Pro, pytest

---

### Task 1: Add failing persistence tests

**Files:**
- Create: `backend/tests/data/test_mongo_index_data.py`

### Task 2: Add Mongo storage module

**Files:**
- Create: `backend/app/data/mongo_index_data.py`
- Test: `backend/tests/data/test_mongo_index_data.py`

### Task 3: Add failing sync-script tests

**Files:**
- Create: `backend/tests/scripts/test_sync_index_scripts.py`

### Task 4: Extend TuShare client and sync scripts

**Files:**
- Modify: `backend/app/data/tushare_client.py`
- Create: `backend/scripts/daily/sync_index_basic.py`
- Create: `backend/scripts/daily/sync_index_daily.py`
- Test: `backend/tests/scripts/test_sync_index_scripts.py`

### Task 5: Run targeted tests and real sync

**Files:**
- Test: `backend/tests/data/test_mongo_index_data.py`
- Test: `backend/tests/scripts/test_sync_index_scripts.py`

### Task 6: Update docs and backlog

**Files:**
- Modify: `docs/tushare_5000积分接口实现对照.md`
- Modify: `docs/plans/2026-03-15-p1-index-data-design.md`
