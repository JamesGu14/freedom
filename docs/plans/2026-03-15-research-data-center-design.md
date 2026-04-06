# 研究数据中心设计

> 日期：2026-03-15  
> 范围：把当前已接入但未充分展示的 TuShare 数据，在前端统一展示出来，并提供一组适合 OpenClaw 调用的聚合 API。

## 1. 目标

当前项目已经接入了大量研究数据，但前端页面主要仍集中在行情、行业、指数和同步状态。财务、分红、股东、筹码、两融、资金流、停复牌等数据虽然已经落库，部分也已有底层 API，但没有形成一套完整、稳定、可导航的研究体验。

本次设计目标是：

- 新增一个独立的“研究数据中心”，而不是继续把所有数据塞进现有个股详情页。
- 新增一层 `research/*` 聚合 API，让前端和 OpenClaw 直接消费可展示、可理解的数据结构。
- 保留现有底层 raw API，不做破坏性迁移。
- 采用分阶段交付方式，优先让高价值数据尽快可见。

## 2. 推荐方案

采用“方案 2”：

- 个股详情页只保留高频核心信息与研究入口。
- 新增研究数据中心，分为个股研究与市场研究两大部分。
- 后端新增 `research/*` 聚合接口，提供摘要、完整列表、趋势数据和页面所需元信息。

不采用的方案：

- 不把所有数据继续堆到 `stocks/[ts_code]`，否则页面和请求都会迅速膨胀。
- 不把每一类数据拆成独立零散页面，否则导航和维护成本过高。

## 3. 信息架构

### 3.1 前端页面结构

建议新增以下页面：

- `/research`
  - 研究数据中心首页
  - 展示入口、说明、常用研究模块
- `/research/stocks/[ts_code]`
  - 个股研究页
- `/research/market`
  - 市场研究页

现有页面调整原则：

- [stocks/[ts_code].js](/home/james/projects/freedom/frontend/pages/stocks/[ts_code].js)
  - 保留 K 线、复权、技术指标等高频内容
  - 新增“进入研究数据中心”入口

### 3.2 个股研究页结构

个股研究页按 4 个模块组织：

1. 财务与分红
2. 股东与筹码
3. 两融与资金流
4. 停复牌与事件

每个模块采用相同模式：

- 顶部摘要卡片
- Tab 或区块切换
- 趋势图 + 明细表格
- 统一的日期范围、分页、空态与错误态

### 3.3 市场研究页结构

市场研究页按 3 个模块组织：

1. 指数
2. 行业
3. 市场资金

首版优先做“指数”，后续再补行业和市场资金。

## 4. 数据映射

### 4.1 个股研究页

#### 财务与分红

- `income`
- `balancesheet`
- `cashflow`
- `fina_indicator`
- `dividend_history`

展示建议：

- 摘要卡片：
  - `roe`
  - `roa`
  - `grossprofit_margin`
  - `debt_to_assets`
  - `eps`
  - 最近一次分红公告
  - 最近一次现金分红
- Tab：
  - 财务指标
  - 利润表
  - 资产负债表
  - 现金流量表
  - 分红送股

#### 股东与筹码

- `stk_holdernumber`
- `top10_holders`
- `top10_floatholders`
- `cyq_perf`
- `cyq_chips`

展示建议：

- 摘要卡片：
  - 最新股东人数
  - 股东人数变化
  - 前十大集中度
  - 前十大流通集中度
  - 最新筹码集中度/获利盘指标
- Tab：
  - 股东人数
  - 前十大股东
  - 前十大流通股东
  - 筹码绩效
  - 筹码分布

#### 两融与资金流

- `margin_detail`
- `moneyflow_dc`
- `hk_hold`
- `ccass_hold`

展示建议：

- 摘要卡片：
  - 最新融资余额
  - 融资余额变化
  - 主力净流入
  - 港股通持股变化
  - CCASS 持股变化
- 区块：
  - 两融趋势
  - 个股资金流
  - 港股通持股
  - CCASS 持股

#### 停复牌与事件

- `suspend_d`
- `stk_surv`
- 后续可扩：`buyback`、`holder_changes`

展示建议：

- 顶部显示最近一次停复牌、最近一次机构调研
- 主视图采用时间线

### 4.2 市场研究页

#### 指数

- `index_basic`
- `index_daily`
- `market_index_dailybasic`
- `index_factor_pro`

#### 行业

- `shenwan_daily`
- `citic_daily`
- `shenwan_industry_member`
- `citic_industry_member`

#### 市场资金

- `moneyflow_hsgt`

## 5. API 设计

### 5.1 总体原则

新增 `research/*` 聚合接口，供前端和 OpenClaw 使用；现有底层接口保留。

接口分层：

- raw API：保留当前 `/stocks/*`、`/market-data/*`、`/agent_required_api/*`
- research API：新增聚合层，返回更适合展示和消费的结构

### 5.2 个股研究 API

#### `/api/research/stocks/{ts_code}/overview`

返回：

- `basic`
- `latest_daily`
- `latest_daily_basic`
- `latest_indicators`
- `latest_financial_indicator`
- `latest_dividend_summary`
- `latest_holder_summary`
- `latest_flow_summary`
- `latest_event_summary`

用途：

- 个股研究页顶部摘要
- OpenClaw 首次抓取入口

#### `/api/research/stocks/{ts_code}/financials`

返回：

- `indicators`
- `income`
- `balance`
- `cashflow`
- `latest_period`
- `periods`

#### `/api/research/stocks/{ts_code}/dividends`

返回：

- `items`
- `summary`
  - `latest_ann_date`
  - `latest_cash_div`
  - `latest_stk_div`
  - `dividend_count`
  - `consecutive_years`

#### `/api/research/stocks/{ts_code}/holders`

返回：

- `holder_number`
- `top10_holders`
- `top10_floatholders`
- `summary`
  - 最新股东人数
  - 股东人数变化
  - 前十大集中度
  - 前十大流通集中度

#### `/api/research/stocks/{ts_code}/chips`

返回：

- `cyq_perf`
- `cyq_chips`
- `summary`
  - 最新筹码集中度
  - 获利盘比例
  - 平均成本区

#### `/api/research/stocks/{ts_code}/flows`

返回：

- `moneyflow_dc`
- `margin_detail`
- `hk_hold`
- `ccass_hold`
- `summary`
  - 最新主力净流入
  - 融资余额
  - 港股通持股变化
  - CCASS 持股变化

#### `/api/research/stocks/{ts_code}/events`

返回：

- `suspend`
- `institution_surveys`
- 预留后续事件字段

### 5.3 市场研究 API

#### `/api/research/market/indexes`

返回：

- `tracked_indexes`
- `latest_snapshot`
- `available_dates`

#### `/api/research/market/indexes/{ts_code}`

返回：

- `basic`
- `daily`
- `dailybasic`
- `factors`

#### `/api/research/market/sectors`

返回：

- `shenwan`
- `citic`
- `latest_trade_date`

#### `/api/research/market/hsgt-flow`

返回：

- `items`
- `summary`

## 6. OpenClaw 适配原则

OpenClaw 应优先调用 `research/*` 接口，而不是自己拼装多个 raw API。

原因：

- 聚合层返回的结构更稳定
- 能减少多次请求
- 可以把摘要、趋势、明细统一打包
- 更适合 Agent 做规划与解释

建议后续给 OpenClaw 的资源划分：

- `stock_overview`
- `stock_financials`
- `stock_dividends`
- `stock_holders`
- `stock_chips`
- `stock_flows`
- `stock_events`
- `market_indexes`
- `market_sectors`
- `market_hsgt_flow`

## 7. 分阶段实施建议

### Phase 1

- 新增个股研究页骨架
- 新增：
  - `overview`
  - `financials`
  - `dividends`
  - `holders`
  - `flows`
  - `events`

### Phase 2

- 接入筹码与更多图表
- 新增市场研究页
- 新增：
  - `market/indexes`
  - `market/indexes/{ts_code}`

### Phase 3

- 行业与市场资金页
- OpenClaw 资源适配与提示词联动

## 8. 风险与约束

- 现有 raw API 来源较散，聚合层必须统一字段命名和缺省值口径。
- 一些数据仍是近几年历史，不是全历史补齐，前端需要展示时间范围而不是暗示“完整全量”。
- `dividend_history` 目前主要是原始分红数据，`dv_ratio`、`payout_ratio`、`consecutive_years` 等衍生字段需要逐步补足。
- `index_daily` 当前只同步了 10 个核心指数白名单，市场研究页要明确这个范围。

## 9. 结论

推荐路线是：

- 新增“研究数据中心”
- 新增 `research/*` 聚合 API
- 个股页保留轻量核心信息
- OpenClaw 以后优先走聚合 API

这条路线既能把当前已接入但未展示的数据真正变成产品能力，也不会继续把现有页面和散接口拖进更高复杂度。
