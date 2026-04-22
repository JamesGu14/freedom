# DuckDB Native Tables → Parquet Migration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Migrate all 8 DuckDB native tables to Parquet files, eliminating DuckDB write lock contention between gunicorn and background scripts.

**Architecture:** Each DuckDB table will be stored as partitioned Parquet files under `data/raw/<table_name>/ts_code=<code>/year=<YYYY>/part-*.parquet`, following the same pattern already used by `daily`, `daily_basic`, and `daily_limit`. Write functions change from DuckDB INSERT to Parquet file append. Read functions change from `SELECT FROM <table>` to `SELECT FROM read_parquet(...)`.

**Tech Stack:** Python 3.11, DuckDB (query engine only, no native tables), Parquet via PyArrow

---

## Current State

13 DuckDB tables, 8 with data, 5 empty:

| Table | Rows | Write Module | Read Modules |
|-------|------|-------------|--------------|
| adj_factor | 1.69M | duckdb_store.py, p0_gap_repair.py | duckdb_store.py, stock_daily_stats.py, agent_required_api.py, audit/adapters.py |
| margin_detail | 2.03M | duckdb_margin.py | research_service.py |
| stk_holdernumber | 259K | duckdb_shareholders.py | research_service.py, sync_top10_holders.py |
| balancesheet | 163K | duckdb_financials.py | research_service.py, sync_dividend.py |
| income | 172K | duckdb_financials.py | research_service.py, sync_dividend.py |
| cashflow | 175K | duckdb_financials.py | research_service.py, sync_dividend.py, agent_required_api.py |
| fina_indicator | 170K | duckdb_financials.py | research_service.py, sync_dividend.py |
| stock_basic | 5.4K | N/A (already migrated to MongoDB) | stocks_service.py (already says "no longer supported") |
| fina_mainbz | 0 | duckdb_financials.py | N/A |
| forecast | 0 | duckdb_financials.py | N/A |
| express | 0 | duckdb_financials.py | N/A |
| fina_audit | 0 | duckdb_financials.py | N/A |
| disclosure_date | 0 | duckdb_financials.py | N/A |

**Note:** `stock_basic` is already fully in MongoDB — the DuckDB table is a vestige with a clear error message. It can be dropped without migration.

## File Structure

### Files to modify (write paths — core changes)

| File | Responsibility |
|------|---------------|
| `backend/app/data/duckdb_store.py` | `upsert_adj_factor()` → write Parquet; `list_adj_factor()` → `read_parquet()` |
| `backend/app/data/duckdb_margin.py` | `upsert_margin_detail()` → write Parquet; read query → `read_parquet()` |
| `backend/app/data/duckdb_financials.py` | `ensure_financial_tables()` → create dirs; all `_upsert_financial_table()` → write Parquet |
| `backend/app/data/duckdb_shareholders.py` | `upsert_stk_holdernumber()` → write Parquet; read query → `read_parquet()` |
| `backend/app/repair/p0_gap_repair.py` | adj_factor batch repair → write Parquet instead of DuckDB INSERT |

### Files to modify (read paths — query changes)

| File | Responsibility |
|------|---------------|
| `backend/app/data/stock_daily_stats.py` | adj_factor reads → `read_parquet()` |
| `backend/app/services/research_service.py` | `_query_duckdb_table()` → generic Parquet read helper; financial table reads |
| `backend/app/services/market_data_service.py` | `_query_parquet()` may need adj_factor path update |
| `backend/app/api/routes/agent_required_api.py` | adj_factor query → `read_parquet()`; margin_detail reads |
| `backend/app/scripts/daily/sync_top10_holders.py` | stk_holdernumber query → `read_parquet()` |
| `backend/app/scripts/daily/sync_dividend.py` | financial table ann_date queries → `read_parquet()` |
| `backend/app/audit/adapters.py` | adj_factor audit adapter → Parquet path |
| `backend/app/audit/registry.py` | adj_factor dataset entry → Parquet config |

### One-time migration script

| File | Responsibility |
|------|---------------|
| `backend/scripts/one_time/export_duckdb_to_parquet.py` | Export all DuckDB tables to partitioned Parquet |

---

## Partition Strategy

All tables use the same pattern as existing Parquet datasets:

```
data/raw/<table_name>/ts_code=<ts_code>/year=<YYYY>/part-*.parquet
```

Date field used for year extraction:

| Table | Date field | Year extraction |
|-------|-----------|----------------|
| adj_factor | trade_date | `trade_date[:4]` |
| margin_detail | trade_date | `trade_date[:4]` |
| stk_holdernumber | ann_date | `ann_date[:4]` |
| balancesheet | ann_date | `ann_date[:4]` |
| income | ann_date | `ann_date[:4]` |
| cashflow | ann_date | `ann_date[:4]` |
| fina_indicator | ann_date | `ann_date[:4]` |
| fina_mainbz | end_date | `end_date[:4]` |
| forecast | ann_date | `ann_date[:4]` |
| express | ann_date | `ann_date[:4]` |
| fina_audit | ann_date | `ann_date[:4]` |
| disclosure_date | ann_date | `ann_date[:4]` |

---

## Tasks

### Task 1: One-time export — DuckDB tables to Parquet

**Files:**
- Create: `backend/scripts/one_time/export_duckdb_to_parquet.py`

- [ ] **Step 1: Write the export script**

```python
#!/usr/bin/env python3
"""One-time migration: export all DuckDB native tables to partitioned Parquet files."""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(SCRIPT_ROOT))

import duckdb
import pandas as pd
from app.core.config import settings

TABLE_CONFIG = {
    "adj_factor": {"date_field": "trade_date"},
    "margin_detail": {"date_field": "trade_date"},
    "stk_holdernumber": {"date_field": "ann_date"},
    "balancesheet": {"date_field": "ann_date"},
    "income": {"date_field": "ann_date"},
    "cashflow": {"date_field": "ann_date"},
    "fina_indicator": {"date_field": "ann_date"},
    "fina_mainbz": {"date_field": "end_date"},
    "forecast": {"date_field": "ann_date"},
    "express": {"date_field": "ann_date"},
    "fina_audit": {"date_field": "ann_date"},
    "disclosure_date": {"date_field": "ann_date"},
}


def export_table(con: duckdb.DuckDBPyConnection, table_name: str, date_field: str) -> None:
    count = con.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0]
    if count == 0:
        print(f"  {table_name}: empty, skipping")
        return

    df = con.execute(f'SELECT * FROM "{table_name}"').fetchdf()
    df[date_field] = df[date_field].astype(str)
    df["year"] = df[date_field].str[:4]

    base_dir = settings.data_dir / "raw" / table_name
    base_dir.mkdir(parents=True, exist_ok=True)

    for (ts_code, year), group in df.groupby(["ts_code", "year"], sort=False):
        partition_dir = base_dir / f"ts_code={ts_code}" / f"year={year}"
        partition_dir.mkdir(parents=True, exist_ok=True)
        part_path = partition_dir / "part-0000.parquet"
        data = group.drop(columns=["year"])
        data.to_parquet(part_path, index=False, engine="pyarrow")

    print(f"  {table_name}: exported {count:,} rows → {base_dir}")


def main() -> None:
    db_path = str(settings.duckdb_path)
    print(f"Reading from: {db_path}")
    con = duckdb.connect(db_path, read_only=True)

    for table_name, config in TABLE_CONFIG.items():
        export_table(con, table_name, config["date_field"])

    con.close()
    print("\nDone! All DuckDB tables exported to Parquet.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the export script**

```bash
cd backend
python scripts/one_time/export_duckdb_to_parquet.py
```

Expected: all 8 tables with data exported to `data/raw/<table>/ts_code=*/year=*/part-0000.parquet`

- [ ] **Step 3: Verify exported Parquet files**

```bash
# Quick sanity check
python3 -c "
import duckdb
con = duckdb.connect('data/quant.duckdb', read_only=True)
for table in ['adj_factor','margin_detail','stk_holdernumber','balancesheet','income','cashflow','fina_indicator']:
    db_count = con.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
    pq_count = con.execute(f\"SELECT COUNT(*) FROM read_parquet('data/raw/{table}/ts_code=*/year=*/*.parquet', union_by_name=true)\").fetchone()[0]
    match = '✅' if db_count == pq_count else '❌'
    print(f'{table}: DuckDB={db_count:,} Parquet={pq_count:,} {match}')
"
```

---

### Task 2: Migrate adj_factor write path (duckdb_store.py)

**Files:**
- Modify: `backend/app/data/duckdb_store.py` — `upsert_adj_factor()` and `list_adj_factor()`

- [ ] **Step 1: Rewrite `upsert_adj_factor()` to write Parquet**

Change the function at line 171 from DuckDB INSERT to Parquet file append, following the same pattern as `upsert_daily()` (line 147). The function should:
1. Ensure `data["trade_date"]` is string
2. Derive `year` from `trade_date[:4]`
3. Group by `(ts_code, year)`
4. Write each group as `data/raw/adj_factor/ts_code=<code>/year=<YYYY>/part-<uuid>.parquet`

- [ ] **Step 2: Rewrite `list_adj_factor()` to read Parquet**

Change the function at line 328 from `SELECT FROM adj_factor WHERE ts_code = ?` to `SELECT FROM read_parquet(?) WHERE ts_code = ?`, following the same pattern as `list_daily()` (line 261). Use glob path `data/raw/adj_factor/ts_code=<code>/year=*/part-*.parquet`.

- [ ] **Step 3: Verify with existing tests or manual check**

```bash
# Check adj_factor read works
python3 -c "
import sys; sys.path.insert(0, 'backend')
from app.data.duckdb_store import list_adj_factor
result = list_adj_factor('000001.SZ', limit=5)
print(f'Got {len(result)} rows')
print(result[0] if result else 'empty')
"
```

---

### Task 3: Migrate margin_detail (duckdb_margin.py)

**Files:**
- Modify: `backend/app/data/duckdb_margin.py`

- [ ] **Step 1: Rewrite `upsert_margin_detail()` to write Parquet**

Change from DuckDB DELETE+INSERT to Parquet append. Since margin_detail may have duplicate keys for the same trade_date+ts_code, the upsert pattern should be:
1. Write new data as Parquet part files (same append pattern as daily)
2. Dedup is handled at compact time (same as daily/daily_basic)

- [ ] **Step 2: Update any read queries to use `read_parquet()`**

Check if `duckdb_margin.py` has read queries and update them.

- [ ] **Step 3: Verify**

```bash
python3 -c "
import sys; sys.path.insert(0, 'backend')
from app.data.duckdb_margin import upsert_margin_detail
import pandas as pd
# Quick read test
import duckdb
con = duckdb.connect('data/quant.duckdb', read_only=True)
count = con.execute(\"SELECT COUNT(*) FROM read_parquet('data/raw/margin_detail/ts_code=*/year=*/*.parquet', union_by_name=true)\").fetchone()[0]
print(f'margin_detail Parquet rows: {count:,}')
"
```

---

### Task 4: Migrate financial tables (duckdb_financials.py)

**Files:**
- Modify: `backend/app/data/duckdb_financials.py`

This is the largest change — handles 9 tables (income, balancesheet, cashflow, fina_indicator, forecast, express, fina_audit, fina_mainbz, disclosure_date).

- [ ] **Step 1: Rewrite `ensure_financial_tables()` → `ensure_financial_dirs()`**

Change from `CREATE TABLE IF NOT EXISTS` to `mkdir(parents=True, exist_ok=True)` for each table's Parquet base directory.

- [ ] **Step 2: Rewrite `_upsert_financial_table()` to write Parquet**

The current pattern is `DELETE FROM <table> USING df WHERE ...` + `INSERT INTO <table>`. Change to:
1. Group incoming df by `(ts_code, year)` where year is derived from the table's date field
2. Append each group as a new Parquet part file
3. Dedup happens at compact time

The key change: replace the `with get_connection(read_only=False)` block with a Parquet write loop.

- [ ] **Step 3: Verify with one financial table**

```bash
python3 -c "
import duckdb
con = duckdb.connect('data/quant.duckdb', read_only=True)
for t in ['income','balancesheet','cashflow','fina_indicator']:
    db = con.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
    try:
        pq = con.execute(f\"SELECT COUNT(*) FROM read_parquet('data/raw/{t}/ts_code=*/year=*/*.parquet', union_by_name=true)\").fetchone()[0]
        match = '✅' if db == pq else '❌'
        print(f'{t}: DuckDB={db:,} Parquet={pq:,} {match}')
    except:
        print(f'{t}: Parquet read error')
"
```

---

### Task 5: Migrate stk_holdernumber (duckdb_shareholders.py)

**Files:**
- Modify: `backend/app/data/duckdb_shareholders.py`

- [ ] **Step 1: Rewrite `ensure_shareholder_tables()` → `ensure_shareholder_dirs()`**

Same pattern as Task 4 — mkdir instead of CREATE TABLE.

- [ ] **Step 2: Rewrite `upsert_stk_holdernumber()` to write Parquet**

Change DELETE+INSERT pattern to Parquet append with `ann_date[:4]` for year partitioning.

- [ ] **Step 3: Verify**

```bash
python3 -c "
import duckdb
con = duckdb.connect('data/quant.duckdb', read_only=True)
db = con.execute('SELECT COUNT(*) FROM stk_holdernumber').fetchone()[0]
pq = con.execute(\"SELECT COUNT(*) FROM read_parquet('data/raw/stk_holdernumber/ts_code=*/year=*/*.parquet', union_by_name=true)\").fetchone()[0]
print(f'stk_holdernumber: DuckDB={db:,} Parquet={pq:,}')
"
```

---

### Task 6: Update read paths across the codebase

**Files:**
- Modify: `backend/app/data/stock_daily_stats.py` — adj_factor reads
- Modify: `backend/app/services/research_service.py` — `_query_duckdb_table()` → Parquet
- Modify: `backend/app/api/routes/agent_required_api.py` — adj_factor query
- Modify: `backend/app/scripts/daily/sync_top10_holders.py` — stk_holdernumber query
- Modify: `backend/app/scripts/daily/sync_dividend.py` — financial table queries
- Modify: `backend/app/audit/adapters.py` — adj_factor audit path
- Modify: `backend/app/audit/registry.py` — adj_factor config

- [ ] **Step 1: Update `research_service.py` — `_query_duckdb_table()`**

This is the main read path for financial tables. Change from:
```python
con.execute(f"SELECT * FROM {table_name} WHERE ts_code = ? ...", params)
```
To:
```python
glob = str(settings.data_dir / "raw" / table_name / "ts_code=*" / "year=*" / "part-*.parquet")
con.execute(f"SELECT * FROM read_parquet(?, union_by_name=true) WHERE ts_code = ? ...", [glob, ...])
```

- [ ] **Step 2: Update `agent_required_api.py` — adj_factor query around line 195**

Change `SELECT trade_date, adj_factor FROM adj_factor WHERE ts_code = ?` to use `read_parquet()`.

- [ ] **Step 3: Update `stock_daily_stats.py` — adj_factor reads**

Change any `SELECT ... FROM adj_factor` to `read_parquet()` queries.

- [ ] **Step 4: Update `sync_top10_holders.py` — stk_holdernumber query**

Change `SELECT DISTINCT ann_date FROM stk_holdernumber` to `read_parquet()`.

- [ ] **Step 5: Update `sync_dividend.py` — financial table ann_date queries**

Change queries like `SELECT DISTINCT ann_date FROM income/balancesheet/cashflow/fina_indicator WHERE ...` to use `read_parquet()`.

- [ ] **Step 6: Update `audit/adapters.py` and `audit/registry.py`**

Change adj_factor audit config from `storage_type="duckdb"` to `storage_type="parquet"` with the correct path.

- [ ] **Step 7: Verify all read paths work**

```bash
# Quick smoke test of key read paths
python3 -c "
import sys; sys.path.insert(0, 'backend')
from app.data.duckdb_store import list_adj_factor
from app.data.duckdb_shareholders import list_stk_holdernumber  # if exists

r = list_adj_factor('000001.SZ', limit=3)
print(f'adj_factor: {len(r)} rows')

import duckdb
con = duckdb.connect('data/quant.duckdb', read_only=True)
for t in ['income','balancesheet','cashflow','fina_indicator','margin_detail','stk_holdernumber']:
    cnt = con.execute(f\"SELECT COUNT(*) FROM read_parquet('data/raw/{t}/ts_code=*/year=*/*.parquet', union_by_name=true)\").fetchone()[0]
    print(f'{t}: {cnt:,} rows in Parquet ✅')
"
```

---

### Task 7: Update p0_gap_repair.py

**Files:**
- Modify: `backend/app/repair/p0_gap_repair.py`

- [ ] **Step 1: Change adj_factor repair to write Parquet**

Replace `INSERT INTO adj_factor` with Parquet file append (same as Task 2's `upsert_adj_factor` pattern).

- [ ] **Step 2: Update repair config**

Change `storage_type: "duckdb"` to `storage_type: "parquet"` for adj_factor.

---

### Task 8: Clean up DuckDB — remove native tables

**Files:**
- Modify: `backend/app/data/duckdb_store.py` — remove `_is_lock_conflict`, `_open_connection` write-path retry, simplify connection manager
- Modify: `backend/scripts/daily/compact_parquet.py` — add new table names to compact dataset choices

- [ ] **Step 1: Add new tables to compact_parquet.py**

Add `adj_factor`, `margin_detail`, `stk_holdernumber`, `income`, `balancesheet`, `cashflow`, `fina_indicator`, `fina_mainbz`, `forecast`, `express`, `fina_audit`, `disclosure_date` to the `--dataset` choices so they can be compacted.

- [ ] **Step 2: Run compact on all new Parquet datasets**

```bash
cd backend
for ds in adj_factor margin_detail stk_holdernumber balancesheet income cashflow fina_indicator; do
    python scripts/daily/compact_parquet.py --dataset $ds --year 2026
done
```

- [ ] **Step 3: Drop DuckDB tables (after confirming everything works)**

```bash
python3 -c "
import duckdb
con = duckdb.connect('data/quant.duckdb', read_only=False)
for t in ['adj_factor','margin_detail','stk_holdernumber','balancesheet','income','cashflow','fina_indicator','fina_mainbz','forecast','express','fina_audit','disclosure_date','stock_basic']:
    try:
        con.execute(f'DROP TABLE IF EXISTS \"{t}\"')
        print(f'Dropped {t}')
    except Exception as e:
        print(f'Failed to drop {t}: {e}')
con.close()
print('All DuckDB tables dropped. quant.duckdb is now empty.')
"
```

- [ ] **Step 4: Verify system still works end-to-end**

```bash
# 1. Check API health
curl --noproxy localhost -s http://localhost:8080/freedom/api/health

# 2. Check stock list
curl --noproxy localhost -s http://localhost:8080/freedom/api/stocks | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'Stocks: {len(d.get(\"items\",d))}')"

# 3. Check K-line data
curl --noproxy localhost -s http://localhost:8080/freedom/api/stocks/000001.SZ/candles | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'Candles: {len(d)} rows')"
```

---

## Risk Mitigation

1. **Backup before migration**: The export script is read-only on DuckDB. Original DuckDB file stays intact until Task 8 Step 3.
2. **Incremental verification**: Each task has a verify step. Don't proceed if verification fails.
3. **Rollback**: If anything breaks, the DuckDB tables still exist (until explicitly dropped). Can revert code changes via git.
4. **Empty tables**: 5 tables (fina_mainbz, forecast, express, fina_audit, disclosure_date) have 0 rows. Migration is trivial — just change the write path, no data to export.

## Estimated effort

- Task 1 (export): 10 min
- Task 2 (adj_factor): 15 min
- Task 3 (margin_detail): 10 min
- Task 4 (financial tables): 20 min
- Task 5 (stk_holdernumber): 10 min
- Task 6 (read paths): 30 min
- Task 7 (gap repair): 10 min
- Task 8 (cleanup): 15 min

**Total: ~2 hours**
