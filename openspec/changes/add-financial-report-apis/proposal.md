## Why

项目已接入财务三表（income / balancesheet / cashflow）和财务指标（fina_indicator），但 TuShare 5000 积分范围内还有 5 个财务相关接口未接入：业绩预告、业绩快报、财务审计意见、主营业务构成、财报披露日期表。这些数据对量化策略（事件驱动、财报季预判）和研究数据中心展示都有直接价值，且全部为低积分接口，接入成本低。

## What Changes

- 在 `tushare_client.py` 新增 5 个 fetch 函数：`fetch_forecast`、`fetch_express`、`fetch_fina_audit`、`fetch_fina_mainbz`、`fetch_disclosure_date`
- 在 `duckdb_financials.py` 新增 5 张 DuckDB 表及对应 upsert 函数
- 扩展 `sync_financial_reports.py` 的 `--dataset` 选项，支持 forecast、express
- 新建 `sync_fina_audit.py`（ts_code 必填，需遍历股票）
- 新建 `sync_fina_mainbz.py`（ts_code 必填，按报告期查询）
- 新建 `sync_disclosure_date.py`（按报告期查全市场）
- 在 `daily.sh`、`backend/scripts/daily/docker-daily.sh` 和 `backend/app/airflow_sync/daily_sync_registry.py` 中补充新 dataset 的调度入口，确保本地脚本、容器脚本和 Airflow 日常同步链路一致
- 更新 `tushare_5000积分接口实现对照.md`，将 5 个接口从"未实现"移到"已实现"

## Capabilities

### New Capabilities
- `financial-forecast-express`: 业绩预告与业绩快报数据的接入、存储和同步
- `financial-audit-mainbz`: 财务审计意见与主营业务构成数据的接入、存储和同步
- `financial-disclosure-date`: 财报披露日期表数据的接入、存储和同步

### Modified Capabilities
<!-- 无需修改已有 spec -->

## Impact

- **后端代码**：`tushare_client.py`、`duckdb_financials.py`、`sync_financial_reports.py`、`sync_fina_audit.py`、`sync_fina_mainbz.py`、`sync_disclosure_date.py`、`daily.sh`、`backend/scripts/daily/docker-daily.sh`、`backend/app/airflow_sync/daily_sync_registry.py`
- **存储**：DuckDB 新增 5 张表（forecast / express / fina_audit / fina_mainbz / disclosure_date）
- **API 额度**：`forecast` / `express` / `disclosure_date` 仍是低频全市场拉取；`fina_audit` 与 `fina_mainbz` 因 `ts_code` 必填，需要按股票遍历。若按全市场执行 `--last-days 30`，单次运行量级接近数千次 TuShare 请求，不能按“每日增加 5-10 次调用”估算，实施时需单独限制调度频率、分批轮转或缩小增量范围
- **前端**：本次不涉及前端改动，后续由研究数据中心统一消费
