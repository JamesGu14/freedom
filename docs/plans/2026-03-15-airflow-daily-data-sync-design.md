# Airflow Daily Data Sync Design

## Scope

- Migrate all current daily-updated TuShare-backed datasets into `ai-personal-os` shared Airflow scheduling.
- Keep data execution independent from the FastAPI service.
- Avoid introducing a third TuShare egress IP.

## Decision

- Shared Airflow will orchestrate the workflow.
- The actual TuShare sync commands will execute on the host machine as the single fixed execution surface.
- Airflow will not call `daily.sh`.
- Airflow will not call Freedom internal APIs for daily sync.
- Airflow will not introduce a new dedicated runner container until egress-IP behavior is proven safe.

## Why this design

- `daily.sh` is a black-box serial script. It is easy to trigger, but hard to observe, retry, or partially rerun.
- Calling FastAPI for core data sync would couple the data pipeline to online service health.
- A new dedicated runner container could introduce another public egress IP and trigger TuShare `IP数量超限`.
- The host machine is already a proven stable TuShare execution surface, so using it as the only scheduler target minimizes risk.

## Scheduling

- DAG location: `ai-personal-os/infra/shared-infra/airflow/dags`
- Timezone: `Asia/Shanghai`
- Schedule: every trading day at `20:30`
- Catchup: `false`
- Max active runs: `1`

## Execution model

```text
shared Airflow
    ├── precheck_trade_day
    ├── market_core
    ├── factor_and_flow
    ├── financials_and_corporate
    ├── holders_and_margin
    ├── index_and_industry
    └── finalize_run
             │
             ▼
host machine
    ├── conda activate freedom
    ├── cd /home/james/projects/freedom
    ├── run one dataset sync script per task
    └── write logs + update local stores
```

## Dataset groups

### 1. market_core

- `pull_daily_history.py`
- `sync_suspend_d.py`

This group covers:
- `daily`
- `daily_basic`
- `daily_limit`
- `adj_factor`
- `suspend_d`

`pull_daily_history.py` stays as one host task because it already owns the tightly-coupled update of `daily / daily_basic / daily_limit / adj_factor`.

### 2. factor_and_flow

- `sync_stk_factor_pro.py`
- `sync_cyq_perf.py`
- `sync_moneyflow_dc.py`
- `sync_moneyflow_hsgt.py`

### 3. financials_and_corporate

- `sync_financial_reports.py --dataset income`
- `sync_financial_reports.py --dataset balancesheet`
- `sync_financial_reports.py --dataset cashflow`
- `sync_financial_reports.py --dataset fina_indicator`
- `sync_dividend.py`

### 4. holders_and_margin

- `sync_holdernumber.py`
- `sync_top10_holders.py --dataset top10_holders`
- `sync_top10_holders.py --dataset top10_floatholders`
- `sync_margin.py`
- `sync_margin_detail.py`

### 5. index_and_industry

- `sync_index_daily.py`
- `sync_shenwan_daily.py`
- `sync_zhishu_data.py --modules daily --skip-members`

This group covers:
- `index_daily`
- `market_index_dailybasic`
- `citic_daily`
- `index_factor_pro`
- `shenwan_daily`

`sync_zhishu_data.py` remains grouped for the currently shared CITIC / market / index-factor path.

## Dependency rules

- `precheck_trade_day` runs first.
- Non-trading day: the DAG exits with all downstream tasks skipped.
- `market_core` runs first among data groups.
- `factor_and_flow` depends on `market_core`.
- `financials_and_corporate`, `holders_and_margin`, and `index_and_industry` can start after `precheck_trade_day`.
- `finalize_run` depends on all upstream groups and writes a concise run summary.

## Criticality

Critical tasks:
- `pull_daily_history.py`
- `sync_stk_factor_pro.py`
- `sync_cyq_perf.py`

If any critical task fails, the DAG run is failed.

Non-critical tasks still fail the DAG in the first phase, but they do not block independent parallel groups from finishing. This keeps diagnostics complete while preserving a simple failure model.

## Retry policy

- Default task retries: `2`
- Default retry delay: `10m`
- Heavy paginated disclosure tasks retries: `3`
- Heavy paginated disclosure retry delay: `15m`

Heavy paginated disclosure tasks:
- `sync_dividend.py`
- `sync_holdernumber.py`
- `sync_top10_holders.py`
- `sync_financial_reports.py` for all datasets

## Host execution wrapper

The DAG should not inline long shell commands repeatedly. Add one host-runner helper layer that:

- activates the `freedom` conda environment
- sets `PYTHONPATH`
- enters `/home/james/projects/freedom`
- runs a single Python sync command
- writes a per-task log file under `logs/airflow_jobs/<dag_id>/<run_id>/`
- returns exit code cleanly to Airflow

This wrapper is a host execution utility, not a new application service.

## Trade-day handling

- Use local `trade_calendar` as the trade-day source of truth.
- At `20:30`, the DAG should still explicitly check whether the execution day is an open `SSE` trading day.
- If not open, skip all data tasks.

## Logging and observability

Per task:
- command
- target date
- started_at
- finished_at
- exit status
- log path

Per DAG run:
- run date
- trade date
- task status summary
- failed task list

First phase can keep the run summary inside Airflow task logs and local log files. It does not need a new Mongo collection yet.

## What is not migrated in this phase

- `daily.sh`
- weekly-only compact tasks
- weekly-only `ccass_hold`, `hk_hold`, `stk_surv`
- weekly audit DAG
- on-demand `index_weight`
- weekly or dictionary-like tasks such as `stock_basic`, `trade_cal`, `index_basic`, `index_classify`, industry members, index members

## Follow-up todo

- Add separate weekly DAGs for weekly-only datasets.
- Revisit whether `sync_zhishu_data.py` should be further split once daily DAG is stable.
- Add notification hooks after the daily DAG becomes stable.
- Re-evaluate a dedicated runner container only after confirming it shares the same TuShare egress IP as the host or fully replaces host execution.
