# Freedom Quant Platform - API 能力范围（Scope）

**版本**: 0.1.0
**标题**: quant-platform

本文档面向 AI Agent（如 KimiClaw）快速理解 Freedom 后端 API 的能力边界。
如需精确参数和返回结构，请同时参考 `docs/openapi.yaml` 或 `docs/openapi.json`。

## 认证方式

除 `/api/health` 和 `/api/auth/*` 外，其余接口通常需要 `Authorization: Bearer <token>`。

## 能力地图（按业务域分组）

### Agent Freedom

- **GET** `/api/agent-freedom/portfolio/accounts/{account_id}` — Get Portfolio Account
  - `account_id` *必填* `string`
- **PUT** `/api/agent-freedom/portfolio/accounts/{account_id}` — Upsert Portfolio Account
  - `account_id` *必填* `string`
- **GET** `/api/agent-freedom/portfolio/positions/{account_id}` — List Portfolio Positions
  - `account_id` *必填* `string`
- **PUT** `/api/agent-freedom/portfolio/positions/{account_id}` — Upsert Portfolio Positions
  - `account_id` *必填* `string`
- **GET** `/api/agent-freedom/report/latest` — Get Latest Report
  - `trade_date` 可选
- **POST** `/api/agent-freedom/run` — Run Agent Freedom
  - `trade_date` 可选
  - `strategy_version_id` 可选
  - `account_id` 可选 `string` 默认: `main`
- **GET** `/api/agent-freedom/runs` — List Runs
  - `start_date` 可选
  - `end_date` 可选
  - `status` 可选
  - `page` 可选 `integer` 默认: `1`
  - `page_size` 可选 `integer` 默认: `50`
- **GET** `/api/agent-freedom/skill-calls` — List Skill Calls
  - `trade_date` 可选
  - `skill` 可选
  - `status` 可选
  - `page` 可选 `integer` 默认: `1`
  - `page_size` 可选 `integer` 默认: `50`

### 中信行业

- **GET** `/api/citic-sectors` — Get Citic Sectors
  - `level` 可选
- **GET** `/api/citic-sectors/{index_code}` — Get Citic Sector Detail
  - `index_code` *必填* `string`
  - `is_new` 可选 默认: `Y`
  - `page` 可选 `integer` 默认: `1`
  - `page_size` 可选 `integer` 默认: `200`

### 交易日历

- **GET** `/api/trade-calendar` — Trade Calendar
  - `exchange` 可选 `string` 默认: `SSE`
  - `start_date` *必填* `string`
  - `end_date` *必填* `string`
  - `is_open` 可选
- **GET** `/api/trade-calendar/latest-trade-date` — Latest Trade Date
  - `exchange` 可选 `string` 默认: `SSE`

### 内部审计

- **POST** `/api/internal/audits/data-integrity/runs` — Create Data Integrity Audit Run
- **GET** `/api/internal/audits/data-integrity/runs/{run_id}` — Get Data Integrity Audit Run
  - `run_id` *必填* `string`
- **POST** `/api/internal/audits/data-integrity/weekly-run` — Create Weekly Airflow Audit Run

### 回测

- **GET** `/api/backtests` — List Backtest Items
  - `page` 可选 `integer` 默认: `1`
  - `page_size` 可选 `integer` 默认: `20`
  - `strategy_id` 可选
  - `strategy_version_id` 可选
  - `status` 可选
- **POST** `/api/backtests` — Create Backtest
- **POST** `/api/backtests/compare` — Compare Backtest Items
- **DELETE** `/api/backtests/{run_id}` — Delete Backtest
  - `run_id` *必填* `string`
- **GET** `/api/backtests/{run_id}` — Get Backtest
  - `run_id` *必填* `string`
- **GET** `/api/backtests/{run_id}/drawdown` — Get Backtest Drawdown Items
  - `run_id` *必填* `string`
- **GET** `/api/backtests/{run_id}/holdings-summary` — Get Backtest Holdings Summary Items
  - `run_id` *必填* `string`
- **GET** `/api/backtests/{run_id}/nav` — Get Backtest Nav Items
  - `run_id` *必填* `string`
- **GET** `/api/backtests/{run_id}/positions` — List Backtest Position Items
  - `run_id` *必填* `string`
  - `page` 可选 `integer` 默认: `1`
  - `page_size` 可选 `integer` 默认: `20`
  - `trade_date` 可选
- **GET** `/api/backtests/{run_id}/signals` — List Backtest Signal Items
  - `run_id` *必填* `string`
  - `page` 可选 `integer` 默认: `1`
  - `page_size` 可选 `integer` 默认: `20`
  - `trade_date` 可选
- **GET** `/api/backtests/{run_id}/trades` — List Backtest Trade Items
  - `run_id` *必填* `string`
  - `page` 可选 `integer` 默认: `1`
  - `page_size` 可选 `integer` 默认: `20`
  - `ts_code` 可选
  - `trade_date` 可选
- **GET** `/api/backtests/{run_id}/trades-by-code` — List Backtest Trade Items By Code
  - `run_id` *必填* `string`
  - `ts_code` *必填* `string`
  - `limit` 可选 `integer` 默认: `5000`

### 宏观数据

- **GET** `/api/macro/cpi-ppi` — Macro Cpi Ppi
  - `start_date` 可选
  - `end_date` 可选
  - `limit` 可选 `integer` 默认: `120`
- **GET** `/api/macro/lpr` — Macro Lpr
  - `start_date` 可选
  - `end_date` 可选
  - `limit` 可选 `integer` 默认: `120`
- **GET** `/api/macro/money-supply` — Macro Money Supply
  - `start_date` 可选
  - `end_date` 可选
  - `limit` 可选 `integer` 默认: `120`
- **GET** `/api/macro/pmi` — Macro Pmi
  - `start_date` 可选
  - `end_date` 可选
  - `limit` 可选 `integer` 默认: `120`
- **GET** `/api/macro/social-financing` — Macro Social Financing
  - `start_date` 可选
  - `end_date` 可选
  - `limit` 可选 `integer` 默认: `120`

### 市场指数

- **GET** `/api/market-index/chart` — Get Market Chart
  - `ts_code` *必填* `string`
  - `limit` 可选 `integer` 默认: `500`
- **GET** `/api/market-index/daily-basic` — Market Index Daily Basic
  - `ts_codes` 可选
  - `trade_date` 可选
  - `start_date` 可选
  - `end_date` 可选
  - `page` 可选 `integer` 默认: `1`
  - `page_size` 可选 `integer` 默认: `500`
- **GET** `/api/market-index/dates` — Get Market Index Dates
  - `limit` 可选 `integer` 默认: `30`
- **GET** `/api/market-index/factors` — Get Market Factors
  - `ts_code` *必填* `string`
  - `source` 可选 `string` 默认: `market`
  - `start_date` 可选
  - `end_date` 可选
  - `limit` 可选 `integer` 默认: `120`
- **GET** `/api/market-index/overview` — Get Market Overview
  - `trade_date` 可选
  - `index_codes` 可选
- **GET** `/api/market-index/series` — Get Market Series
  - `ts_code` *必填* `string`
  - `start_date` 可选
  - `end_date` 可选
  - `limit` 可选 `integer` 默认: `240`

### 市场数据

- **GET** `/api/ccass-hold/{ts_code}` — Ccass Hold
  - `ts_code` *必填* `string`
  - `start_date` *必填* `string`
  - `end_date` *必填* `string`
- **GET** `/api/chip-distribution/{ts_code}` — Chip Distribution
  - `ts_code` *必填* `string`
  - `start_date` *必填* `string`
  - `end_date` *必填* `string`
- **GET** `/api/chip-perf/{ts_code}` — Chip Perf
  - `ts_code` *必填* `string`
  - `start_date` *必填* `string`
  - `end_date` *必填* `string`
- **GET** `/api/hk-hold/{ts_code}` — Hk Hold
  - `ts_code` *必填* `string`
  - `start_date` *必填* `string`
  - `end_date` *必填* `string`
  - `exchange` 可选 `string` 默认: ``
- **GET** `/api/index-factors/{ts_code}` — Index Factors
  - `ts_code` *必填* `string`
  - `start_date` *必填* `string`
  - `end_date` *必填* `string`
- **GET** `/api/institution-survey/{ts_code}` — Institution Survey
  - `ts_code` *必填* `string`
  - `start_date` *必填* `string`
  - `end_date` *必填* `string`
- **GET** `/api/moneyflow-dc/{ts_code}` — Moneyflow Dc
  - `ts_code` *必填* `string`
  - `start_date` *必填* `string`
  - `end_date` *必填* `string`
- **GET** `/api/moneyflow-hsgt` — Moneyflow Hsgt
  - `start_date` *必填* `string`
  - `end_date` *必填* `string`

### 市场状态

- **GET** `/api/market-regime/by-date` — Get Regime By Date Route
  - `trade_date` *必填* `string`
- **GET** `/api/market-regime/history` — Get Regime History Route
  - `limit` 可选 `integer` 默认: `60`
- **GET** `/api/market-regime/latest` — Get Latest Regime Route

### 市场研究

- **GET** `/api/market/events/ma-restructure` — Market Event Ma Restructure
  - `page` 可选 `integer` 默认: `1`
  - `page_size` 可选 `integer` 默认: `200`
- **GET** `/api/market/insider-trades/latest` — Market Insider Trades Latest
  - `trade_type` 可选
  - `days` 可选 `integer` 默认: `30`
  - `min_amount` 可选
  - `page` 可选 `integer` 默认: `1`
  - `page_size` 可选 `integer` 默认: `200`

### 数据同步

- **GET** `/api/data-sync/calendar` — Get Data Sync Calendar
  - `start_date` 可选 `string` 默认: ``
  - `end_date` 可选 `string` 默认: ``
- **GET** `/api/data-sync/missing` — Get Data Sync Missing
  - `start_date` 可选 `string` 默认: ``
  - `end_date` 可选 `string` 默认: ``

### 旧版信号

- **GET** `/api/signal` — Get Signal

### 板块排名

- **GET** `/api/sector-ranking/avg` — Get Sector Ranking Avg
  - `calc_date` 可选
  - `level` 可选 `integer` 默认: `1`
  - `top_n` 可选 `integer` 默认: `10`
  - `bottom_n` 可选 `integer` 默认: `10`
  - `source` 可选 `string` 默认: `sw`
- **GET** `/api/sector-ranking/daily` — Get Sector Ranking Daily
  - `trade_date` 可选
  - `level` 可选 `integer` 默认: `1`
  - `top_n` 可选 `integer` 默认: `5`
  - `bottom_n` 可选 `integer` 默认: `5`
  - `source` 可选 `string` 默认: `sw`
- **GET** `/api/sector-ranking/dates` — Get Sector Ranking Dates
  - `limit` 可选 `integer` 默认: `30`
  - `source` 可选 `string` 默认: `sw`
- **GET** `/api/sector-ranking/history` — Get Sector Ranking History
  - `days` 可选 `integer` 默认: `5`
  - `level` 可选 `integer` 默认: `1`
  - `top_n` 可选 `integer` 默认: `5`
  - `bottom_n` 可选 `integer` 默认: `5`
  - `source` 可选 `string` 默认: `sw`
- **GET** `/api/sector-ranking/level-totals` — Get Sector Ranking Level Totals
  - `source` 可选 `string` 默认: `sw`

### 每日信号

- **GET** `/api/daily-signals` — List Daily Signals
  - `trading_date` 可选
  - `stock_code` 可选
  - `strategy` 可选
  - `signal` 可选
- **GET** `/api/daily-signals/dates` — List Daily Signal Dates
- **GET** `/api/daily-signals/strategies` — List Daily Signal Strategies

### 每日股票信号

- **GET** `/api/daily-stock-signals/by-type` — Get Daily Stock Signal By Type Route
  - `trade_date` *必填* `string`
  - `signal_type` *必填* `string`
- **GET** `/api/daily-stock-signals/dates` — List Daily Stock Signal Dates Route
  - `limit` 可选 `integer` 默认: `365`
- **GET** `/api/daily-stock-signals/overview` — Get Daily Stock Signal Overview Route
  - `trade_date` 可选
  - `top_n` 可选 `integer` 默认: `50`
- **PUT** `/api/daily-stock-signals/resonance/state` — Update Resonance State
- **GET** `/api/daily-stock-signals/statistics` — Get Signal Statistics Route
  - `trade_date` 可选
- **GET** `/api/daily-stock-signals/stock/{ts_code}` — Get Stock Signals Route
  - `ts_code` *必填* `string`
  - `limit_days` 可选 `integer` 默认: `30`
- **GET** `/api/daily-stock-signals/stock/{ts_code}/patterns` — Get Stock Patterns Route
  - `ts_code` *必填* `string`
  - `trade_date` *必填* `string`

### 申万行业

- **GET** `/api/shenwan-industries` — Get Shenwan Industries
  - `version` 可选 默认: `2021`
  - `level` 可选
  - `level1_code` 可选
  - `parent_code` 可选
  - `is_published` 可选
- **GET** `/api/shenwan-industries/versions` — Get Shenwan Versions
- **GET** `/api/shenwan-members` — Get Shenwan Members
  - `ts_code` 可选
  - `l1_code` 可选
  - `l2_code` 可选
  - `l3_code` 可选
  - `is_new` 可选
  - `version` 可选 默认: `2021`
  - `page` 可选 `integer` 默认: `1`
  - `page_size` 可选 `integer` 默认: `200`

### 策略信号

- **GET** `/api/strategy-signals` — List Signals
  - `signal_date` 可选
  - `strategy_version_id` 可选
  - `portfolio_id` 可选
  - `portfolio_type` 可选
  - `signal` 可选
  - `page` 可选 `integer` 默认: `1`
  - `page_size` 可选 `integer` 默认: `20`
- **GET** `/api/strategy-signals/dates` — Get Signal Dates
  - `strategy_version_id` 可选
  - `portfolio_id` 可选 `string` 默认: `__strategy__`
  - `limit` 可选 `integer` 默认: `120`
- **GET** `/api/strategy-signals/latest` — Get Latest Signals
  - `strategy_version_id` 可选
  - `portfolio_id` 可选 `string` 默认: `__strategy__`
  - `portfolio_type` 可选 `string` 默认: `strategy`
  - `page_size` 可选 `integer` 默认: `100`

### 策略管理

- **GET** `/api/strategies` — List Strategy Items
  - `page` 可选 `integer` 默认: `1`
  - `page_size` 可选 `integer` 默认: `20`
  - `status` 可选
  - `keyword` 可选
- **POST** `/api/strategies` — Create Strategy Item
- **GET** `/api/strategies/engine` — List Engine Strategies
- **PUT** `/api/strategies/{strategy_id}` — Update Strategy Item
  - `strategy_id` *必填* `string`
- **POST** `/api/strategies/{strategy_id}/disable` — Disable Strategy Item
  - `strategy_id` *必填* `string`
- **POST** `/api/strategies/{strategy_id}/enable` — Enable Strategy Item
  - `strategy_id` *必填* `string`
- **GET** `/api/strategies/{strategy_id}/versions` — List Versions
  - `strategy_id` *必填* `string`
- **POST** `/api/strategies/{strategy_id}/versions` — Create Strategy Version
  - `strategy_id` *必填* `string`

### 系统

- **GET** `/api/health` — Health Check

### 综合研究

- **GET** `/api/research/market/hsgt-flow` — Research Market Hsgt Flow
  - `start_date` 可选
  - `end_date` 可选
  - `limit` 可选 `integer` 默认: `120`
- **GET** `/api/research/market/indexes` — Research Market Indexes
- **GET** `/api/research/market/indexes/{ts_code}` — Research Market Index Detail
  - `ts_code` *必填* `string`
  - `limit` 可选 `integer` 默认: `240`
- **GET** `/api/research/market/sectors` — Research Market Sectors
  - `limit` 可选 `integer` 默认: `10`
- **GET** `/api/research/stocks/{ts_code}/chips` — Research Stock Chips
  - `ts_code` *必填* `string`
  - `start_date` 可选
  - `end_date` 可选
  - `limit` 可选 `integer` 默认: `120`
- **GET** `/api/research/stocks/{ts_code}/dividends` — Research Stock Dividends
  - `ts_code` *必填* `string`
  - `limit` 可选 `integer` 默认: `100`
- **GET** `/api/research/stocks/{ts_code}/events` — Research Stock Events
  - `ts_code` *必填* `string`
  - `start_date` 可选
  - `end_date` 可选
  - `limit` 可选 `integer` 默认: `120`
- **GET** `/api/research/stocks/{ts_code}/financials` — Research Stock Financials
  - `ts_code` *必填* `string`
  - `limit` 可选 `integer` 默认: `8`
- **GET** `/api/research/stocks/{ts_code}/flows` — Research Stock Flows
  - `ts_code` *必填* `string`
  - `start_date` 可选
  - `end_date` 可选
  - `limit` 可选 `integer` 默认: `120`
- **GET** `/api/research/stocks/{ts_code}/holders` — Research Stock Holders
  - `ts_code` *必填* `string`
  - `limit` 可选 `integer` 默认: `24`
- **GET** `/api/research/stocks/{ts_code}/overview` — Research Stock Overview
  - `ts_code` *必填* `string`

### 股票基础

- **GET** `/api/stocks` — List Stocks
  - `page` 可选 `integer` 默认: `1`
  - `page_size` 可选 `integer` 默认: `10`
  - `name` 可选
  - `ts_code` 可选
  - `industry` 可选
- **GET** `/api/stocks/basic` — Stocks Basic
  - `market` 可选
  - `exchange` 可选
  - `ts_codes` 可选
  - `page` 可选 `integer` 默认: `1`
  - `page_size` 可选 `integer` 默认: `200`
- **GET** `/api/stocks/basic/{ts_code}` — Stock Basic Detail
  - `ts_code` *必填* `string`
- **GET** `/api/stocks/daily-basic/snapshot` — Daily Basic Snapshot
  - `trade_date` 可选
  - `pe_ttm_max` 可选
  - `pb_max` 可选
  - `total_mv_min` 可选
  - `total_mv_max` 可选
  - `dv_ratio_min` 可选
  - `turnover_rate_max` 可选
  - `page` 可选 `integer` 默认: `1`
  - `page_size` 可选 `integer` 默认: `500`
  - `fields` 可选
- **POST** `/api/stocks/daily/batch` — Stock Daily Batch
- **GET** `/api/stocks/daily/snapshot` — Daily Snapshot
  - `trade_date` 可选
  - `ts_codes` 可选
  - `fields` 可选
  - `page` 可选 `integer` 默认: `1`
  - `page_size` 可选 `integer` 默认: `500`
- **POST** `/api/stocks/daily/stats/screen` — Stock Daily Stats Screen
- **GET** `/api/stocks/dividends/screen` — Dividends Screen
  - `dv_ratio_min` 可选
  - `consecutive_years_min` 可选
  - `payout_ratio_max` 可选
  - `total_mv_min` 可选
  - `page` 可选 `integer` 默认: `1`
  - `page_size` 可选 `integer` 默认: `200`
- **POST** `/api/stocks/financials/indicators/batch` — Financial Indicators Batch
- **GET** `/api/stocks/financials/indicators/screen` — Financial Indicators Screen
  - `period` 可选
  - `roe_min` 可选
  - `revenue_yoy_min` 可选
  - `n_income_yoy_min` 可选
  - `debt_to_assets_max` 可选
  - `netprofit_margin_min` 可选
  - `fcf_positive` 可选
  - `page` 可选 `integer` 默认: `1`
  - `page_size` 可选 `integer` 默认: `200`
- **GET** `/api/stocks/indicators/fields` — Stock Indicator Fields
- **GET** `/api/stocks/industries` — List Industries
- **GET** `/api/stocks/limit-prices/snapshot` — Limit Prices Snapshot
  - `trade_date` 可选
  - `ts_codes` 可选
  - `page` 可选 `integer` 默认: `1`
  - `page_size` 可选 `integer` 默认: `500`
- **GET** `/api/stocks/search` — Stocks Search
  - `q` *必填* `string`
  - `limit` 可选 `integer` 默认: `20`
- **POST** `/api/stocks/sync` — Sync Stocks
  - `source` 可选
- **GET** `/api/stocks/{ts_code}/basic` — Get Basic
  - `ts_code` *必填* `string`
- **GET** `/api/stocks/{ts_code}/candles` — Get Candles
  - `ts_code` *必填* `string`
  - `limit` 可选
- **GET** `/api/stocks/{ts_code}/daily` — Stock Daily
  - `ts_code` *必填* `string`
  - `start_date` 可选
  - `end_date` 可选
  - `adj` 可选 `string` 默认: `none`
  - `fields` 可选
- **GET** `/api/stocks/{ts_code}/daily-basic` — Stock Daily Basic
  - `ts_code` *必填* `string`
  - `start_date` 可选
  - `end_date` 可选
  - `fields` 可选
- **GET** `/api/stocks/{ts_code}/daily/recent` — Stock Daily Recent
  - `ts_code` *必填* `string`
  - `n` *必填* `integer`
  - `adj` 可选 `string` 默认: `qfq`
  - `fields` 可选
- **GET** `/api/stocks/{ts_code}/dividends` — Stock Dividends
  - `ts_code` *必填* `string`
  - `limit` 可选 `integer` 默认: `200`
- **GET** `/api/stocks/{ts_code}/dividends/summary` — Stock Dividends Summary
  - `ts_code` *必填* `string`
- **GET** `/api/stocks/{ts_code}/events/buyback` — Stock Event Buyback
  - `ts_code` *必填* `string`
  - `page` 可选 `integer` 默认: `1`
  - `page_size` 可选 `integer` 默认: `200`
- **GET** `/api/stocks/{ts_code}/events/holder-changes` — Stock Event Holder Changes
  - `ts_code` *必填* `string`
  - `page` 可选 `integer` 默认: `1`
  - `page_size` 可选 `integer` 默认: `200`
- **GET** `/api/stocks/{ts_code}/features` — Get Features
  - `ts_code` *必填* `string`
  - `limit` 可选
- **GET** `/api/stocks/{ts_code}/financials/balance` — Financial Balance
  - `ts_code` *必填* `string`
  - `period` 可选
  - `limit` 可选 `integer` 默认: `8`
- **GET** `/api/stocks/{ts_code}/financials/cashflow` — Financial Cashflow
  - `ts_code` *必填* `string`
  - `period` 可选
  - `limit` 可选 `integer` 默认: `8`
- **GET** `/api/stocks/{ts_code}/financials/income` — Financial Income
  - `ts_code` *必填* `string`
  - `period` 可选
  - `limit` 可选 `integer` 默认: `8`
- **GET** `/api/stocks/{ts_code}/financials/indicators` — Financial Indicators
  - `ts_code` *必填* `string`
  - `period` 可选
  - `period_type` 可选 `string` 默认: `quarterly`
  - `limit` 可选 `integer` 默认: `8`
- **GET** `/api/stocks/{ts_code}/indicators` — Stock Indicators
  - `ts_code` *必填* `string`
  - `start_date` 可选
  - `end_date` 可选
  - `fields` 可选
  - `indicators` 可选
  - `format` 可选 `string` 默认: `nested`
- **GET** `/api/stocks/{ts_code}/insider-trades` — Stock Insider Trades
  - `ts_code` *必填* `string`
  - `start_date` 可选
  - `end_date` 可选
  - `holder_type` 可选
  - `trade_type` 可选
  - `page` 可选 `integer` 默认: `1`
  - `page_size` 可选 `integer` 默认: `200`
- **GET** `/api/stocks/{ts_code}/limit-prices` — Stock Limit Prices
  - `ts_code` *必填* `string`
  - `start_date` 可选
  - `end_date` 可选

### 自选股分组

- **GET** `/api/stock-groups` — List Stock Groups
- **POST** `/api/stock-groups` — Create Stock Group
- **DELETE** `/api/stock-groups/{group_id}` — Delete Stock Group
  - `group_id` *必填* `string`
- **GET** `/api/stock-groups/{group_id}` — Get Stock Group
  - `group_id` *必填* `string`
- **PUT** `/api/stock-groups/{group_id}` — Update Stock Group
  - `group_id` *必填* `string`
- **GET** `/api/stock-groups/{group_id}/stocks` — List Group Stocks
  - `group_id` *必填* `string`
- **POST** `/api/stock-groups/{group_id}/stocks` — Add Group Stock
  - `group_id` *必填* `string`
- **DELETE** `/api/stock-groups/{group_id}/stocks/{ts_code}` — Remove Group Stock
  - `group_id` *必填* `string`
  - `ts_code` *必填* `string`
- **PUT** `/api/stock-groups/{group_id}/stocks/{ts_code}` — Update Group Stock
  - `group_id` *必填* `string`
  - `ts_code` *必填* `string`

### 行业数据

- **GET** `/api/industry/citic/daily` — Citic Daily
  - `trade_date` 可选
  - `start_date` 可选
  - `end_date` 可选
  - `level` 可选 `integer` 默认: `1`
  - `industry_code` 可选
  - `page` 可选 `integer` 默认: `1`
  - `page_size` 可选 `integer` 默认: `300`
- **GET** `/api/industry/citic/members` — Citic Members
  - `industry_code` 可选
  - `level` 可选
  - `is_new` 可选 默认: `True`
  - `ts_code` 可选
  - `page` 可选 `integer` 默认: `1`
  - `page_size` 可选 `integer` 默认: `200`
- **GET** `/api/industry/citic/tree` — Citic Tree
  - `level` 可选
- **GET** `/api/industry/shenwan/daily` — Shenwan Daily
  - `trade_date` 可选
  - `start_date` 可选
  - `end_date` 可选
  - `level` 可选 `integer` 默认: `1`
  - `industry_code` 可选
  - `order_by` 可选 `string` 默认: `rank`
  - `page` 可选 `integer` 默认: `1`
  - `page_size` 可选 `integer` 默认: `300`
- **GET** `/api/industry/shenwan/daily/ranking` — Shenwan Daily Ranking
  - `trade_date` 可选
  - `period` 可选 `string` 默认: `1d`
- **GET** `/api/industry/shenwan/members` — Shenwan Members
  - `industry_code` 可选
  - `level` 可选
  - `is_new` 可选 默认: `True`
  - `ts_code` 可选
  - `version` 可选
  - `page` 可选 `integer` 默认: `1`
  - `page_size` 可选 `integer` 默认: `200`
- **GET** `/api/industry/shenwan/tree` — Shenwan Tree
  - `level` 可选
  - `version` 可选

### 行业板块

- **GET** `/api/sectors` — Get Sectors
  - `version` 可选 默认: `2021`
  - `level` 可选 默认: `1`
  - `level1_code` 可选
  - `parent_code` 可选
  - `is_published` 可选 默认: `True`
- **GET** `/api/sectors/members` — Get Sector Members
  - `ts_code` 可选
  - `l1_code` 可选
  - `l2_code` 可选
  - `l3_code` 可选
  - `is_new` 可选 默认: `Y`
  - `version` 可选 默认: `2021`
  - `page` 可选 `integer` 默认: `1`
  - `page_size` 可选 `integer` 默认: `200`
- **GET** `/api/sectors/versions` — Get Sector Versions
- **GET** `/api/sectors/{index_code}` — Get Sector Detail
  - `index_code` *必填* `string`
  - `version` 可选 默认: `2021`
  - `is_new` 可选 默认: `Y`
  - `page` 可选 `integer` 默认: `1`
  - `page_size` 可选 `integer` 默认: `200`

### 认证

- **POST** `/api/auth/login` — Login
- **POST** `/api/auth/logout` — Logout
- **GET** `/api/auth/me` — Me
- **POST** `/api/auth/refresh` — Refresh

## 典型使用场景

1. **查股票/行情**: `search_stocks` → `get_stock_basic` / `get_stock_daily` / `get_stock_indicators`
2. **看行业/板块**: `get_shenwan_industry_tree` / `get_sector_ranking` / `get_citic_members`
3. **财务筛选**: `screen_financials` / `screen_dividends` / `screen_stocks_by_valuation`
4. **交易信号**: `get_daily_signals` / `get_daily_stock_signals_overview` / `get_strategy_signals`
5. **回测验证**: `create_backtest` → `get_backtest` / `get_backtest/{run_id}/nav` / `trades`
6. **深度研究**: `get_stock_overview` / `get_stock_chips` / `get_stock_moneyflow` / `get_stock_events`
7. **宏观/市场**: `get_market_regime` / `get_market_data_overview` / `get_macro_*`
8. **任务/管理**: `list_stock_groups` / `create_stock_group` / `add_stock_to_group`

## 给 AI Agent 的提示

- 股票代码使用 `ts_code` 格式，如 `600519.SH`、`000001.SZ`。
- 日期格式多为 `YYYYMMDD` 或 `YYYY-MM-DD`。
- 分页参数通常是 `page` / `page_size`。
- 涉及 `PUT/POST/DELETE` 的操作可能修改用户数据，调用前建议确认。
