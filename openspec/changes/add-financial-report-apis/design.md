## Context

项目已有成熟的财务数据同步链路：`sync_financial_reports.py` 通过 `--dataset` 参数支持 income / balancesheet / cashflow / fina_indicator 四个数据集，统一使用 DuckDB 存储，按 ann_date 窗口分页拉取（无需指定 ts_code）。

本次新增 5 个接口分为三类查询模式：
- **按公告日期范围查询（不需要 ts_code）**：forecast、express — 与现有接口完全一致
- **按 ts_code + 公告日期范围查询（ts_code 必填）**：fina_audit — 需要遍历股票
- **按 ts_code + 报告期查询（ts_code 必填）**：fina_mainbz — 需要遍历股票，无 ann_date 字段
- **按报告期查全市场**：disclosure_date — end_date 参数 = 报告期，一次返回全市场约 5000 条

只有 forecast 和 express 能直接复用现有的 ann_date 窗口分页逻辑，其余三个查询模式差异太大，需要独立脚本。

## Goals / Non-Goals

**Goals:**
- forecast / express 复用现有 `sync_financial_reports.py`
- fina_audit / fina_mainbz / disclosure_date 各自新建独立同步脚本
- 在 DuckDB 中新增 5 张表，存储关键字段 + raw_payload（与现有模式一致）
- 在 daily.sh 中新增步骤调度同步

**Non-Goals:**
- 不新增 REST API 端点（后续由研究数据中心统一提供）
- 不做前端展示
- 不对现有 4 个 dataset 做任何改动

## Decisions

### 1. 存储全部用 DuckDB，不用 MongoDB

**选择**：5 个新表全部存入 DuckDB（与现有 income / balancesheet / cashflow / fina_indicator 一致）。

**原因**：
- 这 5 个接口都是报表型数据，不是日频行情
- 与现有财务表同一数据域，放在一起方便后续跨表关联查询
- 复用已有的 `duckdb_financials.py` upsert 模式，改动最小

### 2. 按查询模式分组处理

**选择**：

| 接口 | ts_code | 日期参数含义 | 同步方式 |
|------|---------|-------------|---------|
| forecast | 可选 | ann_date 范围 | 扩展 `sync_financial_reports.py` |
| express | 可选 | ann_date 范围 | 扩展 `sync_financial_reports.py` |
| fina_audit | **必填** | ann_date 范围 | 新建 `sync_fina_audit.py`（遍历股票） |
| fina_mainbz | **必填** | **报告期**范围（不是 ann_date） | 新建 `sync_fina_mainbz.py`（遍历股票） |
| disclosure_date | 可选 | end_date = **报告期** | 新建 `sync_disclosure_date.py` |

**原因**：
- forecast / express 可以不传 ts_code 直接按 ann_date 范围查全市场，与现有 income 等完全一致
- fina_audit 要求 ts_code 必填，必须遍历股票列表，与窗口分页模式不兼容
- fina_mainbz 要求 ts_code 必填且日期参数是报告期不是公告日期，双重差异
- disclosure_date 按报告期查全市场，虽然不需要 ts_code，但查询维度完全不同

### 3. fina_audit 的同步策略

**查询模式**：ts_code 必填 + start_date/end_date（公告日期范围）。

**同步逻辑**：
- 从 MongoDB stock_basic 获取全部 ts_code
- 逐只调用 `fetch_fina_audit(ts_code=code, start_date=start, end_date=end)`
- 每只股票通常只有几条审计意见（每年 1 条），数据量极小
- CLI 参数：`--start-date`/`--end-date`（公告日期范围）、`--last-days`、`--ts-codes`（测试用）、`--sleep`

**日常增量**：`--last-days 30`（审计意见在年报季集中发布，30 天窗口足够）

**mark_sync_done**：遍历完所有股票后，按 end_date 标记。

### 4. fina_mainbz 的同步策略

**查询模式**：ts_code 必填 + start_date/end_date（**报告期范围**，不是公告日期）+ period（单个报告期）。

> ⚠️ 注意：fina_mainbz 的 start_date/end_date 含义与其他接口不同。TuShare 文档明确标注为 "Period start date" / "Period end date"，指报告期范围（如 20240101-20241231 表示拉取 20240331/20240630/20240930/20241231 四个报告期的数据），而非公告日期范围。

**同步逻辑**：
- CLI 参数：`--period`（单个报告期）、`--period-start`/`--period-end`（报告期范围，避免与公告日期的 start_date/end_date 混淆）、`--ts-codes`（测试用）、`--sleep`
- 遍历全部股票，逐只调用 fetch
- 分页处理：max 100 条/次，if `len(df) == limit` 则继续翻页

**日常运维**：不加入 daily.sh。每季度手动运行一次 `--period XXXXXXXX`。

**mark_sync_done**：遍历完所有股票后按报告期标记。如果中途失败，不标记 done，下次重跑可覆盖。

### 5. disclosure_date 的同步策略

**查询模式**：按 end_date（报告期）查全市场，max 3000 条/次。

**同步逻辑**：
- CLI 参数：`--year`（遍历 4 个标准报告期）、`--period`（单个报告期）
- 每个报告期全市场约 5000 条，需要 2 次分页请求

**日常调度**：daily.sh 中只查最近 2 个报告期（通过计算当前日期推算哪 2 个报告期可能还在更新），而非全年 4 个。例如 2025 年 6 月，查 20250331 和 20250630。

**mark_sync_done**：按报告期标记。

### 6. daily.sh 调度策略

**选择**：新增 Step 13-16，每个 dataset 作为独立 step（符合现有 daily.sh 的 `run_step_task` 模式）：

```
TOTAL_STEPS=16
Step 13: sync_financial_reports.py --dataset forecast --last-days 7
Step 14: sync_financial_reports.py --dataset express --last-days 7
Step 15: sync_fina_audit.py --last-days 30
Step 16: sync_disclosure_date.py --recent 2
```

- fina_mainbz 不加入 daily.sh（每季度手动运行，在 Step 16 后添加注释说明）
- 每个 step 使用现有 `run_step_task` 函数，自带日志记录和错误输出
- 单个 step 失败时 daily.sh 会因 `set -euo pipefail` 退出。如需容错，可在调用时用 `|| true`，但建议保持现有严格模式（与 Step 1-12 行为一致）

### 7. 表结构：关键字段 + raw_payload

**选择**：每张表保留核心查询字段 + raw_payload JSON 字段。

**原因**：与现有 4 张表一致。核心字段用于过滤和聚合，raw_payload 保留 TuShare 返回的全部原始数据。实现时通过实际 API 调用确认完整字段列表，关键字段以实际返回为准。

## Risks / Trade-offs

- **[fina_audit 遍历耗时]** → 约 5000 只股票，每只 1 条审计意见。`--last-days 30` 时大部分返回空，实际 API 调用约 5000 次 × 1 秒 sleep ≈ 1.5 小时。首次全量拉取耗时较长，daily.sh 中 `--last-days 30` 可控。
- **[fina_mainbz 全量同步耗时]** → 约 5000 只股票，预计 2-3 小时。不加入 daily.sh，每季度手动运行。
- **[fina_mainbz 中途失败]** → 遍历完所有股票后才 mark_sync_done。中途失败不标记，下次重跑时 upsert 保证幂等性。
- **[fina_mainbz 主键可能不唯一]** → 主键 `(ts_code, end_date, bz_item, curr_type)`。如果仍有冲突，raw_payload 兜底。
- **[disclosure_date 分页边界]** → max 3000 条/次，全市场约 5000 条。用 offset 分页，判断 `len(df) < limit` 时停止。
- **[DuckDB 并发写入]** → 所有 dataset 串行同步，不存在并发问题。
- **[数据完整性审计]** → 这 5 个新表暂不加入 data_integrity_audit。现有审计框架基于交易日历做日频缺失检测，而财报数据按公告日期/报告期更新，与交易日历无直接对应关系。后续如需财报完整性校验，应设计独立的审计模式（如按报告期检查覆盖率）。
