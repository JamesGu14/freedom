# Design: 新增9个 TuShare 数据接口

## 架构概览

```
TuShare API
    ↓ (同步脚本 backend/scripts/daily/)
存储层
    ├── Parquet (data/features/<dataset>/ts_code=*/year=*)
    └── MongoDB (集合: cyq_chips, ccass_hold, hk_hold, stk_surv, moneyflow_hsgt)
    ↓
FastAPI 路由 (backend/app/api/routes/market_data.py)
    ↓
openapi.json
```

---

## 1. 存储设计

### 1.1 Parquet 数据集（stock_code × date 矩阵）

#### `cyq_perf` — 每日筹码胜率
```
data/features/cyq_perf/ts_code={ts_code}/year={year}/part-*.parquet
```
字段：`ts_code`, `trade_date`, `his_low`, `his_high`, `cost_5pct`, `cost_15pct`, `cost_50pct`, `cost_85pct`, `cost_95pct`, `weight_avg`, `winner_rate`

主键：`(ts_code, trade_date)`

#### `moneyflow_dc` — 东方财富资金流向（2023-09-11起）
```
data/features/moneyflow_dc/ts_code={ts_code}/year={year}/part-*.parquet
```
字段：`trade_date`, `ts_code`, `name`, `pct_change`, `close`, `net_amount`, `net_amount_rate`, `buy_elg_amount`, `buy_elg_amount_rate`, `buy_lg_amount`, `buy_lg_amount_rate`, `buy_md_amount`, `buy_md_amount_rate`, `buy_sm_amount`, `buy_sm_amount_rate`

主键：`(ts_code, trade_date)`

#### `idx_factor_pro` — 指数技术因子
```
data/features/idx_factor_pro/ts_code={ts_code}/year={year}/part-*.parquet
```
字段（关键子集）：`ts_code`, `trade_date`, `open`, `high`, `low`, `close`, `pre_close`, `change`, `pct_change`, `vol`, `amount`, `macd_bfq`, `macd_dea_bfq`, `macd_dif_bfq`, `kdj_k_bfq`, `kdj_d_bfq`, `kdj_j_bfq`, `rsi_6_bfq`, `rsi_12_bfq`, `boll_upper_bfq`, `boll_mid_bfq`, `boll_lower_bfq`, `ma5_bfq`, `ma10_bfq`, `ma20_bfq`, `ma30_bfq`, `ma60_bfq`, `ma90_bfq`, `ma250_bfq`

主键：`(ts_code, trade_date)`

---

### 1.2 MongoDB 集合

#### `cyq_chips` — 每日筹码分布（全量 Parquet）
```
data/features/cyq_chips/ts_code={ts_code}/year={year}/part-*.parquet
```
字段：`ts_code`, `trade_date`, `price`, `percent`

主键：`(ts_code, trade_date, price)`

预计存储：15–35 GB（Parquet 列压缩后）

#### `ccass_hold` — CCASS持股汇总
```js
// 索引
{ ts_code: 1, trade_date: -1 }
{ trade_date: 1 }

// 文档结构
{
  trade_date: "20250301",
  ts_code: "600519.SH",
  name: "贵州茅台",
  shareholding: "12345678",
  hold_nums: "42",
  hold_ratio: "0.85"
}
```

#### `hk_hold` — 沪深港股通持股明细
```js
// 索引
{ ts_code: 1, trade_date: -1 }
{ trade_date: 1 }
{ exchange: 1, trade_date: -1 }

// 文档结构
{
  code: "600519",
  trade_date: "20250301",
  ts_code: "600519.SH",
  name: "贵州茅台",
  vol: 12345678,
  ratio: 2.34,
  exchange: "SH"
}
```

#### `stk_surv` — 机构调研
```js
// 索引
{ ts_code: 1, surv_date: -1 }
{ surv_date: -1 }

// 文档结构
{
  ts_code: "000001.SZ",
  name: "平安银行",
  surv_date: "20250301",
  fund_visitors: "...",
  rece_place: "...",
  rece_mode: "...",
  rece_org: "...",
  org_type: "...",
  comp_rece: "..."
}
```

#### `moneyflow_hsgt` — 沪深港通资金流向
```js
// 索引
{ trade_date: -1 }  // 唯一键

// 文档结构
{
  trade_date: "20250301",
  ggt_ss: 12.3,
  ggt_sz: -5.6,
  hgt: 45.2,
  sgt: 23.1,
  north_money: 68.3,
  south_money: -15.6
}
```

---

## 2. TuShare Client 扩展

在 `backend/app/data/tushare_client.py` 中新增以下 fetch 函数：

```python
fetch_cyq_perf(ts_code, trade_date, start_date, end_date)
fetch_cyq_chips(ts_code, trade_date)
fetch_ccass_hold(ts_code, trade_date, start_date, end_date)
fetch_hk_hold(ts_code, trade_date, start_date, end_date, exchange)
fetch_stk_surv(ts_code, start_date, end_date)
fetch_moneyflow_dc(ts_code, trade_date, start_date, end_date)
fetch_moneyflow_hsgt(trade_date, start_date, end_date)
fetch_idx_factor_pro(ts_code, trade_date, start_date, end_date)
```

每个函数内部使用已有的 `_request_with_retry` + `_query_pro` 机制。

---

## 3. 同步脚本设计

### 脚本位置与命名约定

```
backend/scripts/daily/
├── sync_cyq_perf.py          # 筹码胜率（Parquet）
├── sync_cyq_chips.py         # 筹码分布（Parquet, 全量历史）
├── sync_ccass_hold.py        # CCASS持股（MongoDB）
├── sync_hk_hold.py           # 港股通持股（MongoDB）
├── sync_stk_surv.py          # 机构调研（MongoDB）
├── sync_moneyflow_dc.py      # DC资金流（Parquet）
├── sync_moneyflow_hsgt.py    # 港通资金流（MongoDB）
└── sync_idx_factor_pro.py    # 指数技术因子（Parquet）
```

### 通用参数接口

所有脚本统一支持：
```
--trade-date YYYYMMDD
--start-date YYYYMMDD
--end-date   YYYYMMDD
--last-days  N
--sleep      SECONDS (default: 1.5)
```

### 分页策略（按接口单次限制）

**原则：尽量按日期批量拉取全市场数据，避免按股票逐只循环（减少 API 调用次数）。**

| API | 单次上限 | 推荐拉取单元 | 说明 |
|-----|---------|------------|------|
| cyq_perf | 5,000 | 按 trade_date | 一次拿全市场当日所有股票，约 5000 条 ✅ |
| cyq_chips | 2,000 | 按 ts_code + 日期段 | 每只股票每日有 100-500 个价位行，按日期批量不可行；改为按 ts_code 拉取全历史，减少总调用次数（5000次 vs 5000×N天次） |
| ccass_hold | 5,000 | 按 trade_date | 一次拿当日所有标的 ✅ |
| hk_hold | 3,800 | 按 trade_date + exchange | 每日3次（SH/SZ/HK各一次）✅ |
| stk_surv | 100 | 按日期段滚动分页 | 100条/次，循环直到结果为空 |
| moneyflow_dc | 6,000 | 按 trade_date | 一次拿全市场当日 ✅ |
| moneyflow_hsgt | 300 | 按日期段 | 300条/次，约覆盖1年，循环分段即可 ✅ |
| idx_factor_pro | 8,000 | 按 ts_code + 日期段 | 全历史约 2000 天，8000条/次够一只指数全量，5年内一次拿完 ✅ |

### Retry 机制

TuShare 偶发超时或限流，所有 fetch 函数统一使用已有的 `_request_with_retry`（`tushare_client.py`），默认配置：
- 最多重试 **4 次**
- 每次退避 `1.2 × attempt` 秒（指数退避）
- 遇到空结果（非报错）**不重试**，直接返回空 DataFrame

各同步脚本的 `--sleep` 参数控制**日期/指数循环间**的主动限速（默认 1.5s），避免触发频次限制。

### Parquet 写入规范

复用 `sync_stk_factor_pro.py` 的模式：
- 按 `(ts_code, year)` 分组
- 写入路径：`data/features/{dataset}/ts_code={ts_code}/year={year}/part-{uuid}.parquet`
- 年度 flush 缓冲：同年数据积攒后一次性写入
- 完成后调用 `mark_sync_done(date, "sync_{dataset}")`

---

## 4. API 路由设计

新建 `backend/app/api/routes/market_data.py`，包含以下端点：

### 筹码数据

```
GET /api/chip-perf/{ts_code}
  ? start_date (YYYYMMDD)
  ? end_date   (YYYYMMDD)
  → { ts_code, items: [{trade_date, his_low, his_high, cost_*, weight_avg, winner_rate}] }

GET /api/chip-distribution/{ts_code}
  ? trade_date  (YYYYMMDD, default: latest)
  → { ts_code, trade_date, items: [{price, percent}] }
```

### 持股数据

```
GET /api/ccass-hold/{ts_code}
  ? start_date
  ? end_date
  → { ts_code, items: [{trade_date, shareholding, hold_nums, hold_ratio}] }

GET /api/hk-hold/{ts_code}
  ? start_date
  ? end_date
  ? exchange (SH|SZ|HK)
  → { ts_code, items: [{trade_date, vol, ratio, exchange}] }
```

### 调研与资金

```
GET /api/institution-survey/{ts_code}
  ? start_date
  ? end_date
  → { ts_code, items: [{surv_date, fund_visitors, rece_org, org_type, ...}] }

GET /api/moneyflow/{ts_code}
  ? start_date
  ? end_date
  ? source (ths|dc, default: ths)
  → { ts_code, source, items: [{trade_date, net_amount, buy_lg_amount, ...}] }

GET /api/moneyflow-hsgt
  ? start_date
  ? end_date
  → { items: [{trade_date, north_money, south_money, hgt, sgt, ...}] }
```

### 指数技术因子

```
GET /api/index-factors/{ts_code}
  ? start_date
  ? end_date
  → { ts_code, items: [{trade_date, close, macd, rsi_6, ma5, ma20, ...}] }
```

### 鉴权

所有新接口与现有接口保持一致，需要 Bearer Token（调用 `/api/auth/login` 获取）。在路由函数签名中依赖注入 `current_user = Depends(get_current_user)`，与现有 routes 写法相同。

### stock_code 兼容

所有 `{ts_code}` 路径参数通过 `resolve_ts_code_input()` 处理，支持：
- `600118` → 查 MongoDB stock_basic → `600118.SH`
- `SH600118` / `600118.SH` → 直接使用

---

## 5. daily.sh 集成

在 `daily.sh` 中新增步骤（当前共7步 → 扩展到13步）：

```bash
# 8) 筹码及胜率
run_step_task "8" "同步每日筹码胜率" \
  "python backend/scripts/daily/sync_cyq_perf.py --start-date ${START_DATE} --end-date ${END_DATE}"

# 9) 筹码分布（滚动60日）
run_step_task "9" "同步每日筹码分布(Parquet)" \
  "python backend/scripts/daily/sync_cyq_chips.py --start-date ${START_DATE} --end-date ${END_DATE}"

# 10) 个股资金流向
run_step_task "10" "同步个股资金流向(DC)" \
  "python backend/scripts/daily/sync_moneyflow_dc.py --start-date ${START_DATE} --end-date ${END_DATE}"

# 11) 沪深港通资金流向
run_step_task "11" "同步港通资金流向" \
  "python backend/scripts/daily/sync_moneyflow_hsgt.py --start-date ${START_DATE} --end-date ${END_DATE}"

# 12) CCASS + 港股通持股（仅周五或按需）
if [[ "${TARGET_WEEKDAY}" == "5" ]]; then
  run_step_task "12" "同步CCASS/港股通持股(每周五)" \
    "python backend/scripts/daily/sync_ccass_hold.py --start-date ${START_DATE} --end-date ${END_DATE} && \
     python backend/scripts/daily/sync_hk_hold.py --start-date ${START_DATE} --end-date ${END_DATE}"
else
  skip_step "12" "同步CCASS/港股通持股(每周五)" "非周五"
fi

# 13) 指数技术因子
run_step_task "13" "同步指数技术因子" \
  "python backend/scripts/daily/sync_idx_factor_pro.py --start-date ${START_DATE} --end-date ${END_DATE}"
```

注：`stk_surv` 为事件驱动，**每周五**随 shenwan 成员同步一同运行，拉取最近7天的新增调研记录。

---

## 6. openapi.json 更新策略

FastAPI 通过 `GET /api/openapi.json` 自动生成 schema（已在 `main.py` 中配置 `openapi_url`）。新路由注册后，schema 自动包含所有新端点，无需手动维护文件。外部服务直接调用该端点获取最新 schema。
