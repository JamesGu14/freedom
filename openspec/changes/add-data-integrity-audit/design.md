# Design: 本地数据完整性审计

## 设计目标

新增一套离线审计能力，对当前仓库中的日频数据源进行本地完整性检查，不依赖云端对账，不修改业务数据，只输出报告。

审计的核心问题分成两类：

1. 数据集在其本地存在区间内，是否缺少某些交易日。
2. 对于个股类日频矩阵数据，某个交易日的数据覆盖是否明显落后于 `daily` 基准面。

## 审计范围

### A. 个股日频矩阵

- `daily`
- `daily_basic`
- `daily_limit`
- `indicators`
- `adj_factor`
- `cyq_perf`
- `moneyflow_dc`

### B. 市场/指数日频

- `shenwan_daily`
- `citic_daily`
- `market_index_dailybasic`
- Mongo `index_factor_pro`
- `moneyflow_hsgt`

### 首版排除

- 非日频或事件型数据：`stk_surv`、`stock_basic`、行业成员数据
- 子集覆盖且规则特殊的数据：`ccass_hold`、`hk_hold`
- 价格分布型大数据：`cyq_chips`

## 核心口径

### 1. 时间边界

每个数据集的审计起点使用“该数据集本地最早日期”，终点使用“该数据集本地最晚日期”。

这意味着：

- 不要求 `moneyflow_dc` 回补到 2010 年以前；
- 不要求 `cyq_perf` 在 2018 年前存在数据；
- 报告只对数据集自身已经出现的历史区间负责。

### 2. 交易日基准

统一使用 `trade_calendar(exchange=SSE)` 作为交易日基准。

在某个数据集的 `[local_min_date, local_max_date]` 区间内：

- 取其中所有交易日作为“应有日期集合”
- 与数据集实际日期集合做差，得到缺失交易日

例外：

- `moneyflow_hsgt` 不再直接使用 `SSE` 交易日历作为缺失判定基准。
- 真实运行中已验证 TuShare 在部分 `SSE` 开市日不会返回 `moneyflow_hsgt` 数据，这更像沪深港通自身的可交易日口径，而不是本地缺失。
- 因此该数据集首版采用“本地日期范围信息性审计”，不再把 `SSE` 额外交易日直接判定为缺口。
- `moneyflow_dc` 仍使用 `SSE` 交易日历作为主基准，但允许维护极少量“已验证源头空日”豁免列表。
- 当前已确认 `20231122` 在 TuShare 单日查询与区间查询中都不返回数据，因此不再将该日判定为本地缺失。

### 3. 覆盖基准

个股类数据源统一以 `daily` 当日实际存在的 `ts_code` 集合作为基准。

原因：

- 更贴近“本地研究数据是否齐套”
- 避免直接使用 `stock_basic` 造成停牌、退市、历史边界等伪缺失

实际落地后，覆盖基准进一步细化为“`daily` 基准 + 数据集特定排除规则”：

- `daily_basic`
  - 排除 `.BJ` 后缀；
  - 排除 `600018.SH`，因为该股票在早期历史段会被 `daily` 计入，但源头 `daily_basic` 长期不返回。
- `daily_limit`
  - 排除 `.BJ` 后缀；
  - 排除 `001914.SZ`，因为其长期历史表现更像接口覆盖边界，而不是本地漏写。
- `cyq_perf`
  - 排除 `.BJ` 后缀；
  - 排除 `300114.SZ`、`600898.SH`，因为真实运行中已验证 TuShare `cyq_perf` 在对应日期段不返回这两只股票。

这样做的目的不是“放松审计”，而是把“源头口径差异”与“本地漏写”拆开，避免把接口能力边界误判为本地缺口。

### 4. 指数因子口径

仓库中同时存在两条指数因子数据线：

- Parquet `features/idx_factor_pro`
- Mongo `index_factor_pro`

首版审计只覆盖 Mongo `index_factor_pro`，原因是它属于当前在线业务链路的一部分，并与 `market_index_dailybasic`、`citic_daily`、`shenwan_daily` 共同构成现有指数/板块数据面。

## 架构草图

```text
trade_calendar
    ↓
dataset registry
    ├── parquet / duckdb / mongo
    ├── date field
    ├── audit mode
    └── baseline rule
    ↓
audit engine
    ├── date gap audit
    ├── coverage audit
    └── rowcount anomaly audit
    ↓
report builder
    ├── summary.md
    ├── missing_dates.csv
    ├── coverage_anomalies.csv
    ├── rowcount_anomalies.csv
    └── summary.json
```

## 数据集注册表

建议引入一个 registry，统一描述审计对象。例如：

```text
dataset_name
storage_type
location
date_field
audit_mode
baseline_dataset
coverage_key
severity_policy
```

### 审计模式

- `date_only`
  - 只检查日期缺口
- `date_and_coverage`
  - 检查日期缺口
  - 检查相对 `daily` 的个股覆盖率
- `date_and_rowcount`
  - 检查日期缺口
  - 检查每日总记录数异常

## 审计器设计

### Date Gap Audit

输入：
- 数据集实际日期集合
- `trade_calendar` 交易日集合

输出：
- `local_min_date`
- `local_max_date`
- `expected_trade_dates`
- `actual_trade_dates`
- `missing_trade_dates`
- 连续缺失区间摘要

### Coverage Audit

仅适用于个股类数据集。

步骤：

1. 计算 `daily` 每个交易日的 `distinct ts_code` 数量。
2. 计算目标数据集每个交易日的 `distinct ts_code` 数量。
3. 做日期对齐，输出：
   - `daily_count`
   - `dataset_count`
   - `missing_count`
   - `coverage_ratio`

必要时可对异常日期下钻，输出少量缺失股票样本，但首版不是必须。

### Rowcount Anomaly Audit

适用于市场/指数类日频集合。

步骤：

1. 统计数据集每日 `row_count`
2. 计算最近 20 个有效交易日的中位数
3. 如果某日记录数相对中位数明显下降，则标记异常

这个检查可以捕获“日期没缺，但当天只写入了一部分”的情况。

`moneyflow_hsgt` 不适用该检查，首版仅做 `date_only`。

真实运行后，这一规则又补充了两个约束：

- 如果某个市场/指数类数据集从某一日开始进入新的稳定平台期，并且后续多个交易日都维持相同记录数，则优先视为“口径切换”而不是“持续异常”。
- `market_index_dailybasic` 的 `20100531` 已确认属于早期指数清单过渡日，当前按已知单日切换点白名单处理。

## 结果分级

### Green

- 无缺失交易日
- 覆盖率或记录数波动在容忍区间内

### Yellow

- 存在少量缺失交易日
  或
- 存在轻度覆盖异常 / 记录数异常

### Red

- 存在连续交易日缺失
  或
- 覆盖率明显偏低
  或
- 记录数异常严重

### 默认阈值

- 覆盖率 `>= 99.9%`：Green
- 覆盖率 `>= 99.0%` 且 `< 99.9%`：Yellow
- 覆盖率 `< 99.0%`：Red
- 记录数相对近 20 个有效交易日中位数下降 `> 20%`：Yellow
- 记录数相对近 20 个有效交易日中位数下降 `> 50%`：Red

## 报告格式

### `summary.md`

面向人工阅读，至少包含：

- 运行时间
- 审计数据集数量
- 红黄绿统计
- 每个数据集的摘要结论

### `missing_dates.csv`

建议字段：

- `dataset`
- `trade_date`
- `issue_type`
- `severity`

### `coverage_anomalies.csv`

建议字段：

- `dataset`
- `trade_date`
- `daily_count`
- `dataset_count`
- `missing_count`
- `coverage_ratio`
- `severity`

### `rowcount_anomalies.csv`

建议字段：

- `dataset`
- `trade_date`
- `row_count`
- `median_20d`
- `deviation_ratio`
- `severity`

### `summary.json`

用于后续接 Airflow 或定时调度系统。

## 输出目录

首版报告目录固定为：

```text
logs/data_audit/<run_id>/
```

其中 `<run_id>` 建议使用时间戳或时间戳加随机后缀，保证多次运行结果互不覆盖。

## 调度集成

在离线脚本之外，当前设计已经补充一个独立 Airflow 周期任务：

- DAG ID：`freedom_data_integrity_weekly`
- 调度：每周六 `06:00`，时区 `Asia/Shanghai`
- 任务类型：两个 `PythonOperator`
- 职责：
  - 共享 Airflow 先调用 Freedom 内部接口 `POST /api/internal/audits/data-integrity/runs`
  - 随后轮询 `GET /api/internal/audits/data-integrity/runs/{run_id}` 直到成功或失败
  - 审计执行仍发生在 Freedom 本地进程内，文件报告保留在 `logs/data_audit/<run_id>/`
  - 运行状态与最终摘要统一写入 MongoDB `data_integrity_audit_runs`
  - 共享部署位置：`/home/james/projects/ai-personal-os/infra/shared-infra/airflow/dags/freedom_data_integrity_weekly.py`

Mongo 运行摘要至少包含：

- `run_id`
- `dag_id`
- `task_id`
- `scheduled_for`
- `output_dir`
- `status_summary`
- `datasets`
- `summary`
- `created_at`
- `updated_at`

## 性能考虑

首版默认只做聚合层面的审计：

- 日期集合扫描
- 每日 `distinct ts_code` 覆盖统计
- 每日总记录数统计

不做全量股票明细反连接，避免在本地大数据集上制造过高开销。

## 运行经验

在当前仓库的真实数据上，已经观察到两类与设计相关的经验结论：

### 1. `adj_factor` 缺失更像可回补的真实缺口

- 历史审计曾将 `adj_factor` 标为大面积缺失。
- 后续通过宿主机串行请求 TuShare 并回写 DuckDB 后，该数据集已恢复为：
  - `missing_dates=0`
  - `coverage_anomalies=0`

这说明 `adj_factor` 的异常与“真实缺数据”高度一致，适合继续使用当前日期缺口 + 覆盖率口径。

### 2. `index_factor_pro` 的 `rowcount` 异常需要数据集特定口径

- `index_factor_pro` 的历史缺失交易日已可通过本地 Parquet 回灌和宿主机串行 TuShare 回补清零。
- 在补齐历史缺失后，`2025-07` 之后的异常日期一度集中表现为 MongoDB 行数低于本地 `data/features/idx_factor_pro` Parquet。
- 后续已经实现“同日本地 Parquet 行数优先”的 `rowcount` 参考口径，并用本地 Parquet 对该批日期完成回灌。

这意味着：

- 对 `index_factor_pro` 来说，统一使用“最近 20 日中位数”作为唯一 `rowcount` 基线不够稳健；
- 本地 Parquet 是更贴近真实口径的优先参考面；
- 在参考口径与本地回灌同时到位后，该数据集已达到：
  - `missing_dates=0`
  - `rowcount_anomalies=0`

因此，`index_factor_pro` 后续应继续沿用更具体的异常口径，例如：

- 按来源分层比较 `market / sw / ci`
- 基于本地 Parquet 的同日参考行数做校验
- 或按阶段切分中位数窗口，避免跨口径时期直接比较

### 3. `daily_basic` / `daily_limit` / `cyq_perf` 的大量红灯并不等于大量本地缺数

在真实审计与回补过程中，最终确认这三类覆盖异常混合了两种问题：

- 一部分是本地真实缺口，例如 `daily_basic` / `daily_limit` 在 `2025-01-02 ~ 2025-01-27` 的一批股票记录漏写；
- 另一部分是源头接口覆盖边界，例如 `.BJ` 历史口径差异、`cyq_perf` 对个别股票长期不返回。

因此后续口径调整为：

- 先在基准面排除已确认的接口边界；
- 再对剩余覆盖异常做定点回补；
- 最终以“剩余异常是否仍然存在”来判断本地是否真的不完整。

该策略已经在真实数据上验证有效，三者当前均可达到：

- `missing_dates=0`
- `coverage_anomalies=0`

### 4. 当前最新基线

截至 `2026-03-14`，最新全量审计报告 `logs/data_audit/full_audit_20260314_all_green_final/` 的结果为：

- `12 / 12` 数据集全部 `green`
- `missing_dates=0`
- `coverage_anomalies=0`
- `rowcount_anomalies=0`

- 先做日期级与聚合级扫描，不直接对所有数据集执行全量明细反连接。
- 对大 Parquet 数据集优先使用 `DISTINCT trade_date`、`COUNT(DISTINCT ts_code)` 这类聚合。
- 报告中如果需要缺失股票样本，限制为异常日期抽样输出。
- 首版不纳入 `cyq_chips`，避免价格分布型数据拖垮审计时间。

## 已知预期现象

基于当前本地盘点，`adj_factor` 的本地日期区间明显短于 `daily`，预计首版审计会直接给出高优先级异常提示。这个结果应视为有效发现，而不是误报。
