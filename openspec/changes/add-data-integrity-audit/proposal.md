# Proposal: 新增本地数据完整性审计能力

## Why

当前平台已经积累了多类本地数据源，包括个股日线、技术因子、行业日线、指数因子与资金流数据，但缺少一个统一的审计入口来判断这些数据在日期维度和覆盖维度上是否完整。

**Context**:
- 数据分散存储在 Parquet、DuckDB 和 MongoDB 中，人工检查成本高且容易遗漏。
- 同步任务历史上经历过脚本调整和临时方案，部分数据源的起始日期与覆盖范围并不一致。
- 当前目标是把系统首先当作个人量化研究平台的数据源项目来建设，需要优先确认本地研究数据是否齐套。

**Current state**:
- 现有能力只能零散查看单个数据源或通过 `data_sync_date` 粗略判断任务是否跑过。
- 缺少面向“数据集”级别的完整性报告，无法快速识别整天缺失、局部缺失或明显异常的时间段。

**Desired state**:
- 平台可以运行一个本地审计脚本，对所有日频数据源按统一口径进行完整性扫描。
- 审计结果能够输出人类可读的 Markdown 报告，以及 CSV/JSON 明细，支持后续接入 Airflow 或周期性巡检。

## What Changes

- 新增“本地数据完整性审计”变更，覆盖日频数据源的日期缺口与覆盖异常检查。
- 引入统一的数据集注册表，声明每个数据集的存储位置、日期字段、审计模式与基准规则。
- 以 `daily` 作为个股类日频数据的基准面，对 `daily_basic`、`daily_limit`、`indicators`、`adj_factor`、`cyq_perf`、`moneyflow_dc` 做覆盖审计。
- 对市场/指数类日频数据做日期缺口与记录数异常检查，包括 `shenwan_daily`、`citic_daily`、`market_index_dailybasic`、Mongo `index_factor_pro`。
- 对 `moneyflow_hsgt` 仅做日期缺口检查。
- 输出统一的审计报告目录 `logs/data_audit/<run_id>/`，至少包含 Markdown 总报告、缺失日期明细、覆盖异常明细与 JSON 摘要。
- 首版排除非日频或事件型数据，例如 `stk_surv`、`stock_basic`、行业成员变更、`ccass_hold`、`hk_hold`、`cyq_chips`。

## Impact

### Affected Specifications
- `openspec/specs/data-integrity-audit/spec.md` - 新增本地数据完整性审计能力的正式需求。

### Affected Code
- `backend/scripts/` - 新增审计总入口脚本与支持模块。
- `backend/app/data/` - 复用现有 MongoDB、DuckDB、Parquet 读取能力。
- `logs/` 或新的报告输出目录 - 存储审计产物。

### User Impact
- 管理者可以在本地一键生成数据完整性报告，快速定位历史缺漏与异常覆盖日期。
- 后续迁移到 Airflow 时，可以直接复用相同的审计脚本或其输出格式。

### API Changes
- 无新增对外 API。
- 本次变更以离线审计脚本和报告产物为主。

### Migration Required
- [ ] Database migration
- [ ] API version bump
- [ ] User communication needed
- [x] Documentation updates

## Timeline Estimate

中等规模变更。主要复杂度在于统一不同存储后端的审计口径，以及控制大体量 Parquet 扫描的成本。

## Risks

- 大体量 Parquet 数据集可能导致全量扫描耗时过长。
  - 缓解：先做日期级聚合，再对可疑区间下钻；`cyq_chips` 暂不纳入首版。
- `idx_factor_pro` 同时存在 Parquet 与 Mongo 两条数据线，若不明确范围，容易导致审计结果口径混乱。
  - 缓解：首版明确只审当前在线业务主链路使用的 Mongo `index_factor_pro`。
- 不同数据集的业务起始日期不同，若口径定义不清晰，会产生伪缺失。
  - 缓解：统一采用“从该数据集本地首日开始审计”，并在报告中显式展示首日与末日。
- 个股覆盖率直接以 `stock_basic` 为基准会放大停牌/退市噪音。
  - 缓解：明确以 `daily` 当日实际股票集合为基准。
