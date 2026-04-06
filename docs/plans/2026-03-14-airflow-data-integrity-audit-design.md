# Airflow Weekly Data Integrity Audit Design

## Goal

把现有本地数据完整性审计脚本接入 Airflow，形成一个独立的每周任务，并在保留 `logs/data_audit/<run_id>/` 文件报告的同时，把每次运行结果落到 MongoDB。

## Scope

- 新增一个独立 Airflow DAG
- 每周六 `06:00` `Asia/Shanghai` 运行
- DAG 只负责数据完整性审计，不接管 `daily.sh`
- 每次运行后，把审计摘要写入 MongoDB

## Non-Goals

- 不改现有 `daily.sh` 主数据链路
- 不新增后端 API
- 不把 Airflow 结果展示接进前端

## Recommended Shape

使用单个 `PythonOperator` 完成“执行审计 + 落 MongoDB”。

原因：

- 现有审计入口已经是 Python 内部函数 `run_audit(...)`
- 这次只需要一个独立任务，不需要复杂编排
- 单任务最容易部署，也最不容易和现有 Airflow 雏形冲突

## DAG Design

- DAG ID：`freedom_data_integrity_weekly`
- Schedule：`0 6 * * 6`
- Timezone：`Asia/Shanghai`
- `catchup=False`
- `max_active_runs=1`
- 单任务：
  - `run_weekly_data_integrity_audit`

## Execution Flow

```text
Airflow DAG
   ↓
PythonOperator
   ↓
run_audit(run_id=...)
   ├── write logs/data_audit/<run_id>/
   └── return AuditRunResult
   ↓
build Mongo document
   ↓
upsert data_integrity_audit_runs
```

## Mongo Storage

新增集合：`data_integrity_audit_runs`

建议字段：

- `run_id`
- `dag_id`
- `task_id`
- `schedule`
- `scheduled_for`
- `output_dir`
- `status_summary`
- `datasets`
- `summary`
- `created_at`
- `updated_at`

其中：

- `status_summary` 保存 `green/yellow/red` 聚合计数
- `datasets` 保存每个数据集的状态、缺失数、异常数
- `summary` 保存机器可读摘要，方便后续做 API 或看板

## Indexes

- 唯一索引：`run_id`
- 普通索引：`scheduled_for` 倒序
- 普通索引：`created_at` 倒序

## Verification

- 单元测试覆盖：
  - 审计运行结果如何转换成 Mongo 文档
  - Mongo upsert helper 是否按预期写入与建索引
- 手工验证：
  - 运行 DAG callable
  - 检查 `logs/data_audit/<run_id>/`
  - 检查 Mongo `data_integrity_audit_runs`

## Expected Outcome

完成后，Airflow 可以每周自动运行一次本地完整性审计，并把结果同时保存在：

- 文件系统：`logs/data_audit/<run_id>/`
- MongoDB：`data_integrity_audit_runs`
