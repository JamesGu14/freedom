# idx_factor_pro Quota Protection Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Prevent `sync_idx_factor_pro.py` from wasting the remaining run after TuShare daily quota exhaustion, and make failed codes easy to replay.

**Architecture:** Keep the existing year-partition resume logic, but add a quota-specific stop path that aborts the outer loop once the API reports the daily limit. Persist per-run failed codes to a text file under `logs/`, and allow later replay through a `--ts-codes-file` input.

**Tech Stack:** Python 3.11, argparse, pathlib, logging, tqdm, existing TuShare client and parquet partition layout.

---

### Task 1: Add replay input

**Files:**
- Modify: `backend/scripts/daily/sync_idx_factor_pro.py`

**Step 1:** Add `--ts-codes` and `--ts-codes-file` CLI options.
**Step 2:** Add a resolver that merges explicit codes, file-based codes, and the default Mongo-derived index list.
**Step 3:** Keep ordering stable and remove duplicates.

### Task 2: Add quota fuse

**Files:**
- Modify: `backend/scripts/daily/sync_idx_factor_pro.py`

**Step 1:** Detect the TuShare daily quota error string from exceptions.
**Step 2:** Return a dedicated result status for quota exhaustion instead of treating it like a normal per-code failure.
**Step 3:** Stop the outer loop immediately when that status appears.

### Task 3: Persist failed codes

**Files:**
- Modify: `backend/scripts/daily/sync_idx_factor_pro.py`

**Step 1:** Collect failed codes during the run.
**Step 2:** Write them to `logs/idx_factor_pro_failed_<timestamp>.txt`.
**Step 3:** Log the path so the next run can use it directly.

### Task 4: Validate

**Files:**
- Modify: `backend/scripts/daily/sync_idx_factor_pro.py`

**Step 1:** Run `python backend/scripts/daily/sync_idx_factor_pro.py --help`.
**Step 2:** Run a lightweight syntax check.
**Step 3:** Document the exact resume commands for today.
