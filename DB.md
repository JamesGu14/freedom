# 数据存储总览（DuckDB / Parquet / MongoDB）

本文总结当前项目里三种存储分别保存什么数据，以及主要由哪些脚本读写。

## 1. DuckDB

- 数据库文件：`data/quant.duckdb`
- 作用定位：本地分析引擎 + 少量结构化表存储

当前主要表：

| 表名 | 主要内容 | 主要写入来源 | 主要读取来源 |
|---|---|---|---|
| `adj_factor` | 个股复权因子（`ts_code + trade_date + adj_factor`） | `backend/scripts/daily/pull_daily_history.py` | `backend/app/api/routes/stocks.py` 的 `/stocks/{ts_code}/candles` |

说明：

- 日线、指标等大体量时序数据现在主要放在 Parquet，DuckDB 通过 `read_parquet(...)` 查询。
- 股票基础信息存储在 MongoDB 的 `stock_basic` 集合。

## 2. Parquet

- 根目录：`data/`
- 作用定位：大体量时序行情和因子明细（按分区落盘，便于增量追加）

当前核心目录：

| 路径 | 分区方式 | 数据内容 | 主要写入来源 |
|---|---|---|---|
| `data/raw/daily/` | `ts_code/year` | 个股日线（OHLCV、涨跌幅等） | `backend/scripts/daily/pull_daily_history.py`、`backend/scripts/one_time/pull_stock_history.py` |
| `data/raw/daily_basic/` | `ts_code/year` | 个股每日指标（估值、换手、市值等） | `backend/scripts/one_time/pull_stock_history.py` |
| `data/raw/daily_limit/` | `ts_code/year` | 涨跌停价格数据 | `backend/scripts/one_time/pull_stock_history.py` |
| `data/features/indicators/` | `ts_code/year` | 个股技术面因子（MA/MACD/KDJ/RSI 等） | `backend/scripts/daily/sync_stk_factor_pro.py` |

说明：

- API 读取时通过 `backend/app/data/duckdb_store.py` 使用 DuckDB 的 `read_parquet` 统一查询。
- 分区写入是 append 方式，日常可用 `backend/scripts/daily/compact_parquet.py` 做去重压缩。

## 3. MongoDB

- 连接配置：`backend/app/core/config.py` 中 `mongodb_url`
- 数据库名：`freedom`（`mongodb_db`）
- 作用定位：业务元数据、用户权限、策略信号、行业/指数结构化数据

当前集合：

| 集合名 | 主要内容 | 主要写入来源 |
|---|---|---|
| `users` | 用户账号、密码哈希、状态、登录时间 | 启动初始化 + 用户管理接口 |
| `refresh_tokens` | 刷新令牌及吊销状态 | 登录/刷新流程 |
| `stock_basic` | 股票基础信息（当前主库存储） | `/api/stocks/sync` + TuShare 同步 |
| `stock_groups` | 自选组定义 | 自选组接口 |
| `stock_group_items` | 自选组内股票关系 | 自选组接口 |
| `trade_calendar` | 交易日历（SSE） | 交易日历同步逻辑 |
| `daily_signal` | 每日策略信号（BUY/SELL/HOLD） | `backend/scripts/daily/calculate_signal.py` |
| `shenwan_industry` | 申万行业层级定义 | `backend/scripts/one_time/sync_shenwan_industry.py` |
| `shenwan_industry_member` | 申万行业成分股 | `backend/scripts/daily/sync_shenwan_members.py` |
| `shenwan_daily` | 申万行业指数日行情与排名 | `backend/scripts/daily/sync_shenwan_daily.py` |
| `citic_industry` | 中信行业层级定义 | `backend/scripts/daily/sync_zhishu_data.py` |
| `citic_industry_member` | 中信行业成分股 | `backend/scripts/daily/sync_zhishu_data.py` |
| `citic_daily` | 中信行业指数日行情与排名 | `backend/scripts/daily/sync_zhishu_data.py` |
| `market_index_dailybasic` | 大盘指数每日指标（估值/市值等） | `backend/scripts/daily/sync_zhishu_data.py` |
| `index_factor_pro` | 指数技术面因子（含 `source=market/sw/ci`） | `backend/scripts/daily/sync_zhishu_data.py` |

说明：

- "大盘指数、申万指数、中信指数"的技术因子统一落在 `index_factor_pro`，通过 `source` 区分。
- 板块排名页面主要依赖 `shenwan_daily` 与 `citic_daily`。

## 4. 时序数据日期范围汇总

统计截至 2026-02-07，所有包含 `trade_date`（或等价日期字段）的数据源的覆盖范围。

### DuckDB

| 表名 | 日期字段 | 起始日期 | 结束日期 | 总行数 | 股票/指数数 |
|---|---|---|---|---|---|
| `adj_factor` | `trade_date` | 20250102 | 20260206 | 234,435 | 5,540 |

### Parquet

| 路径 | 日期字段 | 起始日期 | 结束日期 | 总行数 | 股票数 | 文件数 |
|---|---|---|---|---|---|---|
| `data/raw/daily/` | `trade_date` | 20000104 | 20260206 | 15,463,161 | 5,510 | 73,850 |
| `data/raw/daily_basic/` | `trade_date` | 20000104 | 20260109 | 15,263,161 | 5,467 | 72,793 |
| `data/raw/daily_limit/` | `trade_date` | 20070104 | 20260109 | 14,023,010 | 5,465 | 65,255 |
| `data/features/indicators/` | `trade_date` | 20100315 | 20260206 | 13,733,220 | 5,977 | 67,421 |

### MongoDB

| 集合名 | 日期字段 | 起始日期 | 结束日期 | 总行数 | 股票/指数数 | 备注 |
|---|---|---|---|---|---|---|
| `trade_calendar` | `cal_date` | 20000101 | 20261231 | 9,862 | — | 交易所=SSE |
| `daily_signal` | `trading_date` | 20250102 | 20260206 | 5,069 | 3,311 | 策略: **DailySignalModel**, EarlyBreakoutSignalModel |
| `shenwan_daily` | `trade_date` | 20100104 | 20260206 | 1,903,597 | 689 | 申万行业指数日行情 |
| `citic_daily` | `trade_date` | 20100104 | 20260206 | 1,617,995 | 594 | 中信行业指数日行情 |
| `market_index_dailybasic` | `trade_date` | 20100104 | 20260206 | 19,454 | 5 | 大盘指数每日估值 |
| `index_factor_pro` | `trade_date` | 20050104 | 20260206 | 723,063 | 879 | source: market/sw/ci |

## 5. Parquet 数据完整性检查（20100101-20260207）

以 `trade_calendar`（SSE）中的交易日为基准，检查范围：20100104-20260206（共 3,911 个交易日）。

| 路径 | 状态 | 缺失交易日数 | 缺失区间 |
|---|---|---|---|
| `data/raw/daily/` | **完整** | 0 | — |
| `data/raw/daily_basic/` | **完整** | 0 | — |
| `data/raw/daily_limit/` | **完整** | 0 | — |
| `data/features/indicators/` | **完整** | 0 | — |

`daily_basic` 和 `daily_limit` 已加入 `pull_daily_history.py` 的每日拉取流程，无需单独补数据。
