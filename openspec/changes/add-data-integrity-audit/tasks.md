# Tasks: 本地数据完整性审计

## Phase 1: 范围与基础设施

- [x] T1 新增审计入口脚本
  - 统一加载 trade_calendar
  - 统一管理报告输出目录
  - 支持最小必要参数，例如输出目录、是否限制数据集、是否限制日期范围

- [x] T2 新增数据集注册表
  - 为每个日频数据集声明存储类型、位置、日期字段、审计模式、基准规则
  - 明确 `index_factor_pro` 首版只审 Mongo 集合，不审 Parquet `features/idx_factor_pro`
  - 明确 `moneyflow_hsgt` 使用 `date_only` 规则
  - 明确首版排除的数据集

## Phase 2: 核心审计能力

- [x] T3 实现日期缺口审计
  - 支持 Parquet、DuckDB、MongoDB 三类后端
  - 输出本地首日、末日、应有交易日数、实际交易日数、缺失交易日列表

- [x] T4 实现个股覆盖审计
  - 以 `daily` 为基准
  - 对 `daily_basic`、`daily_limit`、`indicators`、`adj_factor`、`cyq_perf`、`moneyflow_dc` 输出每日覆盖率

- [x] T5 实现市场/指数记录数异常审计
  - 对 `shenwan_daily`、`citic_daily`、`market_index_dailybasic`、Mongo `index_factor_pro` 输出每日记录数及异常标记
  - 不对 `moneyflow_hsgt` 执行记录数异常检查

- [x] T6 定义统一的异常分级规则
  - `green / yellow / red`
  - 兼容日期缺口、覆盖异常、记录数异常三类结论
  - 默认覆盖率阈值固定为 `99.9% / 99.0%`
  - 默认记录数异常阈值固定为相对近 20 日中位数 `20% / 50%`

## Phase 3: 报告输出

- [x] T7 生成 Markdown 总报告
  - 提供总览、红黄绿摘要、每个数据集的关键结论
  - 输出目录固定为 `logs/data_audit/<run_id>/`

- [x] T8 生成 CSV 明细
  - `missing_dates.csv`
  - `coverage_anomalies.csv`
  - `rowcount_anomalies.csv`

- [x] T9 生成 JSON 摘要
  - 方便后续接入 Airflow 或外部调度系统

## Phase 4: 验证与文档

- [x] T10 使用当前本地数据运行一次审计
  - 验证各数据集的本地首末日期识别是否正确
  - 验证 `adj_factor` 等已知异常是否被正确报告

- [x] T11 补充使用说明
  - 如何运行审计
  - 如何理解红黄绿结论
  - 如何查看输出目录中的报告

- [x] T12 记录第二阶段候选范围
  - `cyq_chips`
  - `ccass_hold`
  - `hk_hold`
  - 缺失股票样本下钻

## Follow-up Notes

- [x] F1 为 `index_factor_pro` 增加数据集特定的 `rowcount` 基线口径
  - 已支持使用同日本地 `features/idx_factor_pro` Parquet 行数作为优先参考基线
  - 当前 `index_factor_pro` 在修复缺失日并完成本地回灌后，已达到 `missing_dates=0`、`rowcount_anomalies=0`

- [x] F2 为股票矩阵覆盖审计增加数据集特定基准过滤
  - 已支持在 `daily` 基准上按数据集排除少量后缀或 `ts_code`
  - 当前 `daily_basic`、`daily_limit`、`cyq_perf` 已全部达到 `coverage_anomalies=0`

- [x] F3 为市场类 `rowcount` 审计增加口径切换抑制与单日白名单
  - 已支持自动抑制持续稳定的新平台期，避免把永久口径切换误报成持续异常
  - `market_index_dailybasic` 已对 `20100531` 启用已知切换点白名单
  - 当前 `shenwan_daily`、`citic_daily`、`market_index_dailybasic` 已全部达到 `rowcount_anomalies=0`

- [x] F4 完成全量收口验证
  - 最新全量报告：`logs/data_audit/full_audit_20260314_all_green_final/`
  - 当前结果：`12 / 12 green`
