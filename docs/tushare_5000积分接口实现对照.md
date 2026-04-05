# TuShare 5000 积分接口实现对照

> 更新时间：2026-03-15（晚）  
> 对照来源：[docs/tushare_5000积分可用接口.csv](/home/james/projects/freedom/docs/tushare_5000积分可用接口.csv)  
> 代码依据：`backend/app/data/tushare_client.py`、`backend/scripts/daily/*`、`backend/scripts/one_time/*`  
> 完整度依据：`logs/data_audit/full_audit_20260314_all_green_final/summary.json` 与当前本地 MongoDB / DuckDB / Parquet 扫描结果

## 1. 口径说明

- 本文只把 `docs/tushare_5000积分可用接口.csv` 里的 179 个接口作为主对照范围。
- 其中有少量同名接口分属不同分类，比如 `交易日历` 同时出现在 `股票数据` 和 `期货数据` 下。本文按 `一级分类 + 二级分类 + 接口名称` 三元组判断，不按名字模糊匹配。
- “已实现”分两种：
  - `已实现并形成本地数据集`：仓库里已有同步入口，并且落到了 MongoDB / DuckDB / Parquet。
  - `已实现但仅按需调用`：代码里已经接入 TuShare 接口，但没有形成本地持久化表。
- “完整度”分两种口径：
  - 对已纳入本地审计器的日频数据，直接引用红黄绿结果。
  - 对未纳入日频审计的数据，只给出当前本地行数、日期范围或结构说明，不把它们误写成“完整”。

## 2. 总览

### 2.1 按 CSV 接口数统计

- CSV 接口总数：179
- 已实现并形成本地数据集：28
- 已实现但仅按需调用：1
- 尚未实现：150

### 2.2 已实现接口分布

- `股票数据`：20 个
- `指数专题`：9 个
  - 其中 8 个已经形成本地数据集
  - 1 个是按需调用，不落库

### 2.3 仓库里额外接入、但不在这份 CSV 内的 TuShare 接口

这些接口不计入上面的 179 个 CSV 统计，但仓库里已经有实现：

- `stk_factor_pro` -> `features/indicators`
- `idx_factor_pro` -> `index_factor_pro` 与 `features/idx_factor_pro`
- `cyq_perf` -> `features/cyq_perf`
- `cyq_chips` -> `features/cyq_chips`

## 3. 已实现接口清单

### 3.1 已实现并形成本地数据集


| CSV 分类            | 接口名称       | TuShare API / 调用方式     | 本地表名 / 数据类型名                             | 存储      | 同步入口                                                                                           | 当前完整度                                                                 |
| ----------------- | ---------- | ---------------------- | ---------------------------------------- | ------- | ---------------------------------------------------------------------------------------------- | --------------------------------------------------------------------- |
| 股票数据 / 基础数据       | 股票列表       | `stock_basic`          | `stock_basic`                            | MongoDB | `app/services/stocks_service.py` + `POST /api/stocks/sync`                                     | 未纳入日频完整性审计；当前 `5473` 条，`list_date` 范围 `19901219 ~ 20260121`           |
| 股票数据 / 基础数据       | 交易日历       | `trade_cal`            | `trade_calendar`                         | MongoDB | `backend/scripts/one_time/sync_trade_calendar.py`                                              | 未单独做红黄绿判定；当前 `9862` 条，`cal_date` 范围 `20000101 ~ 20261231`，并被用作全局交易日基准 |
| 股票数据 / 行情数据       | 历史日线       | `pro.daily(...)`       | `raw/daily`                              | Parquet | `backend/scripts/daily/pull_daily_history.py`、`backend/scripts/one_time/pull_stock_history.py` | `green`；范围 `20000104 ~ 20260306`，缺失交易日 `0`                            |
| 股票数据 / 行情数据       | 复权因子       | `pro.adj_factor(...)`  | `adj_factor`                             | DuckDB  | `backend/scripts/daily/pull_daily_history.py`、`backend/scripts/daily/sync_adj_factor.py`       | `green`；范围 `20000104 ~ 20260306`，缺失交易日 `0`，覆盖异常 `0`                  |
| 股票数据 / 行情数据       | 每日指标       | `pro.daily_basic(...)` | `raw/daily_basic`                        | Parquet | `backend/scripts/daily/pull_daily_history.py`、`backend/scripts/one_time/pull_stock_history.py` | `green`；范围 `20000104 ~ 20260306`，缺失交易日 `0`，覆盖异常 `0`                 |
| 股票数据 / 行情数据       | 每日涨跌停价格    | `pro.stk_limit(...)`   | `raw/daily_limit`                        | Parquet | `backend/scripts/daily/pull_daily_history.py`、`backend/scripts/one_time/pull_stock_history.py` | `green`；范围 `20070104 ~ 20260306`，缺失交易日 `0`，覆盖异常 `0`                  |
| 股票数据 / 行情数据       | 每日停复牌信息    | `suspend_d`            | `suspend_d`                              | MongoDB | `backend/scripts/daily/sync_suspend_d.py`                                                       | 未纳入当前日频审计；当前 `8358` 条，`trade_date` 范围 `20240102 ~ 20260313`        |
| 股票数据 / 财务数据       | 利润表        | `income`               | `income`                                 | DuckDB  | `backend/scripts/daily/sync_financial_reports.py --dataset income`                              | 未纳入当前财务审计；当前 `172504` 行，`ann_date` 范围 `20200103 ~ 20260314`，`end_date` 范围 `20161231 ~ 20251231` |
| 股票数据 / 财务数据       | 资产负债表      | `balancesheet`         | `balancesheet`                           | DuckDB  | `backend/scripts/daily/sync_financial_reports.py --dataset balancesheet`                        | 未纳入当前财务审计；当前 `163730` 行，`ann_date` 范围 `20200103 ~ 20260314`，`end_date` 范围 `20161231 ~ 20251231` |
| 股票数据 / 财务数据       | 现金流量表      | `cashflow`             | `cashflow`                               | DuckDB  | `backend/scripts/daily/sync_financial_reports.py --dataset cashflow`                            | 未纳入当前财务审计；当前 `175535` 行，`ann_date` 范围 `20200103 ~ 20260314`，`end_date` 范围 `20161231 ~ 20251231` |
| 股票数据 / 财务数据       | 财务指标数据     | `fina_indicator`       | `fina_indicator`                         | DuckDB  | `backend/scripts/daily/sync_financial_reports.py --dataset fina_indicator`                      | 未纳入当前财务审计；当前 `170361` 行，`ann_date` 范围 `20200408 ~ 20260314`，`end_date` 范围 `20200331 ~ 20251231` |
| 股票数据 / 财务数据       | 分红送股数据     | `dividend`             | `dividend_history`                       | MongoDB | `backend/scripts/daily/sync_dividend.py`                                                         | 未纳入当前专项审计；当前 `43174` 条，`ann_date` 范围 `20240104 ~ 20260314`，`end_date` 范围 `20230930 ~ 20260116` |
| 股票数据 / 股东及股本      | 股东人数       | `stk_holdernumber`     | `stk_holdernumber`                       | DuckDB  | `backend/scripts/daily/sync_holdernumber.py`                                                    | 未纳入当前专项审计；当前 `259305` 行，`ann_date` 范围 `20200101 ~ 20260314`，`end_date` 范围 `20020628 ~ 20260312` |
| 股票数据 / 股东及股本      | 前十大股东      | `top10_holders`        | `top10_holders`                          | MongoDB | `backend/scripts/daily/sync_top10_holders.py --dataset top10_holders`                           | 未纳入当前专项审计；当前 `460361` 条，`ann_date` 范围 `20240102 ~ 20251114`，`end_date` 范围 `20211231 ~ 20250930` |
| 股票数据 / 股东及股本      | 前十大流通股东    | `top10_floatholders`   | `top10_floatholders`                     | MongoDB | `backend/scripts/daily/sync_top10_holders.py --dataset top10_floatholders`                      | 未纳入当前专项审计；当前 `459172` 条，`ann_date` 范围 `20240102 ~ 20251114`，`end_date` 范围 `20230630 ~ 20250930` |
| 股票数据 / 特色数据       | 中央结算系统持股统计 | `ccass_hold`           | `ccass_hold`                             | MongoDB | `backend/scripts/daily/sync_ccass_hold.py`                                                     | 未纳入当前日频审计；当前 `3304561` 条，`trade_date` 范围 `20201111 ~ 20260304`        |
| 股票数据 / 特色数据       | 沪深股通持股明细   | `hk_hold`              | `hk_hold`                                | MongoDB | `backend/scripts/daily/sync_hk_hold.py`                                                        | 未纳入当前日频审计；当前 `5620746` 条，`trade_date` 范围 `20160629 ~ 20260305`        |
| 股票数据 / 特色数据       | 机构调研数据     | `stk_surv`             | `stk_surv`                               | MongoDB | `backend/scripts/daily/sync_stk_surv.py`                                                       | 未纳入当前日频审计；当前 `90139` 条，`surv_date` 范围 `20210811 ~ 20260302`           |
| 股票数据 / 两融及转融通     | 融资融券交易汇总   | `margin`               | `margin`                                 | MongoDB | `backend/scripts/daily/sync_margin.py`                                                          | 未纳入当前专项审计；当前 `1585` 条，`trade_date` 范围 `20240102 ~ 20260313`         |
| 股票数据 / 两融及转融通     | 融资融券交易明细   | `margin_detail`        | `margin_detail`                          | DuckDB  | `backend/scripts/daily/sync_margin_detail.py`                                                   | 未纳入当前专项审计；当前 `2035361` 行，`trade_date` 范围 `20240102 ~ 20260313`     |
| 股票数据 / 资金流向数据     | 个股资金流向（DC） | `moneyflow_dc`         | `features/moneyflow_dc`                  | Parquet | `backend/scripts/daily/sync_moneyflow_dc.py`                                                   | `green`；范围 `20230911 ~ 20260305`，缺失交易日 `0`，覆盖异常 `0`                  |
| 股票数据 / 资金流向数据     | 沪深港通资金流向   | `moneyflow_hsgt`       | `moneyflow_hsgt`                         | MongoDB | `backend/scripts/daily/sync_moneyflow_hsgt.py`                                                 | `green`；范围 `20150105 ~ 20260305`，缺失交易日 `0`                             |
| 指数专题 / 指数基本信息     | 指数基本信息     | `index_basic`          | `index_basic`                            | MongoDB | `backend/scripts/daily/sync_index_basic.py`                                                     | 未纳入当前专项审计；当前 `10076` 条，覆盖 `SSE/SZSE/CSI/CICC/SW/MSCI` 六个市场         |
| 指数专题 / 指数日线行情     | 指数日线行情     | `index_daily`          | `index_daily`                            | MongoDB | `backend/scripts/daily/sync_index_daily.py`                                                     | 未纳入当前专项审计；当前 `4946` 条，`trade_date` 范围 `20240102 ~ 20260313`，首轮仅同步 10 个核心指数白名单 |
| 指数专题 / 大盘指数每日指标   | 大盘指数每日指标   | `index_dailybasic`     | `market_index_dailybasic`                | MongoDB | `backend/scripts/daily/sync_zhishu_data.py`                                                    | `green`；范围 `20100104 ~ 20260306`，缺失交易日 `0`，记录数异常 `0`                |
| 指数专题 / 申万行业分类     | 申万行业分类     | `index_classify`       | `shenwan_industry`                       | MongoDB | `backend/scripts/one_time/sync_shenwan_industry.py`                                            | 未纳入当前日频审计；当前 `870` 条，主要是分类字典数据                                        |
| 指数专题 / 申万行业成分（分级） | 申万行业成分（分级） | `index_member_all`     | `shenwan_industry_member`                | MongoDB | `backend/scripts/daily/sync_shenwan_members.py`                                                | 未纳入当前日频审计；当前 `3002` 条，属于成分变更类数据                                       |
| 指数专题 / 申万行业指数日行情  | 申万行业指数日行情  | `sw_daily`             | `shenwan_daily`                          | MongoDB | `backend/scripts/daily/sync_shenwan_daily.py`                                                  | `green`；范围 `20100104 ~ 20260306`，缺失交易日 `0`，记录数异常 `0`                 |
| 指数专题 / 中信行业成分     | 中信行业成分     | `ci_index_member`      | `citic_industry`、`citic_industry_member` | MongoDB | `backend/scripts/daily/sync_zhishu_data.py`                                                    | 未纳入当前日频审计；当前 `citic_industry=414`、`citic_industry_member=5000`        |
| 指数专题 / 中信行业指数日行情  | 中信行业指数日行情  | `ci_daily`             | `citic_daily`                            | MongoDB | `backend/scripts/daily/sync_zhishu_data.py`                                                    | `green`；范围 `20100104 ~ 20260306`，缺失交易日 `0`，记录数异常 `0`                 |


### 3.2 已实现但仅按需调用


| CSV 分类         | 接口名称    | TuShare API / 调用方式 | 当前实现方式                                                                       | 本地表名 / 数据类型名 | 完整度                    |
| -------------- | ------- | ------------------ | ---------------------------------------------------------------------------- | ------------ | ---------------------- |
| 指数专题 / 指数成分和权重 | 指数成分和权重 | `index_weight`     | 仅在 `backend/app/quant/engine.py` 中调用 `fetch_index_weight()` 动态拉取，用于组合/指数成分解析 | 无持久化表        | 不适用；当前没有本地沉淀，也未纳入完整性审计 |


## 4. 已实现但不在这份 CSV 里的 TuShare 接口

这部分不是 `docs/tushare_5000积分可用接口.csv` 的对照对象，但它们确实已经进入仓库，后面做数据治理时不能漏掉。


| TuShare API      | 本地表名 / 数据类型名              | 存储      | 同步入口                                           | 当前完整度                                                 |
| ---------------- | ------------------------- | ------- | ---------------------------------------------- | ----------------------------------------------------- |
| `stk_factor_pro` | `features/indicators`     | Parquet | `backend/scripts/daily/sync_stk_factor_pro.py` | `green`；范围 `20100104 ~ 20260306`，缺失交易日 `0`，覆盖异常 `0`   |
| `idx_factor_pro` | `index_factor_pro`        | MongoDB | `backend/scripts/daily/sync_zhishu_data.py`    | `green`；范围 `20050104 ~ 20260306`，缺失交易日 `0`，记录数异常 `0`  |
| `idx_factor_pro` | `features/idx_factor_pro` | Parquet | `backend/scripts/daily/sync_idx_factor_pro.py` | 未纳入当前首版审计；当前 `1582921` 条，范围 `20150105 ~ 20260306`     |
| `cyq_perf`       | `features/cyq_perf`       | Parquet | `backend/scripts/daily/sync_cyq_perf.py`       | `green`；范围 `20180102 ~ 20260305`，缺失交易日 `0`，覆盖异常 `0`  |
| `cyq_chips`      | `features/cyq_chips`      | Parquet | `backend/scripts/daily/sync_cyq_chips.py`      | 未纳入当前首版审计；当前 `233818215` 条，范围 `20180102 ~ 20260306`   |


## 5. 关键观察

### 5.1 当前已落地接口的完整性结论

- 当前已纳入首版审计的 12 个日频数据集，最新状态已经全部为 `green`。
- 这批结果不是单纯靠“放宽规则”得到的，而是由两部分组成：
  - 真实缺口回补，例如 `adj_factor`、`index_factor_pro`、`daily_basic`、`daily_limit`
  - 审计口径修正，例如 `moneyflow_hsgt`、`moneyflow_dc`、市场类 `rowcount` 平台切换抑制
- 当前最重要的结论已经从“哪些数据源是红灯”切换成“哪些规则需要长期维护”，例如：
  - `moneyflow_hsgt` 不应强绑 `SSE` 全交易日历
  - `moneyflow_dc` 存在已验证的单日源头空值
  - `daily_basic`、`daily_limit`、`cyq_perf` 需要少量数据集特定基准排除
  - `shenwan_daily`、`citic_daily` 等市场类数据需要避免把永久口径切换误报成持续异常

### 5.2 “一个 CSV 接口 -> 多个本地数据集”的情况

- `中信行业成分`
  - 不是只落一张表。
  - 当前同步过程会同时维护：
    - `citic_industry`
    - `citic_industry_member`
- `申万行业成分（分级）`
  - 当前实现落的是 `shenwan_industry_member`
  - 对应的分类字典 `shenwan_industry` 来自另一条 `index_classify` 同步链路

### 5.3 当前仓库里最容易混淆的双存储

- `idx_factor_pro`
  - 现在同时存在：
    - Mongo `index_factor_pro`
    - Parquet `features/idx_factor_pro`
  - 前者更贴近当前在线业务链路，后者更像离线特征/扩展 API 数据集。
  - 这不是单纯的“误重复”，但会带来口径混乱，后面最好统一治理。

### 5.4 当前没有实现的高价值接口

如果只从“个人量化研究平台”的直接价值看，后续优先级较高的未实现接口大概会是这些：

- `融资融券标的（盘前）`
- `股东增减持`
- `ETF日线行情`
- `ETF基本信息`

## 6. 尚未实现的 CSV 接口清单

以下列表按 `一级分类` 聚合，表示 `docs/tushare_5000积分可用接口.csv` 中目前仍未在仓库里落地的接口。

### 6.1 股票数据（71 个）

每日股本（盘前）、ST股票列表、ST风险警示板股票、沪深港通股票列表、股票曾用名、上市公司基本信息、上市公司管理层、管理层薪酬和持股、北交所新旧代码对照、IPO新股上市、股票历史列表、周线行情、月线行情、复权行情、周/月线行情(每日更新)、周/月线复权行情(每日更新)、通用行情接口、沪深股通十大成交股、港股通十大成交股、港股通每日成交统计、港股通每月成交统计、备用行情、业绩预告、业绩快报、财务审计意见、主营业务构成、财报披露日期表、股权质押统计数据、股权质押明细数据、股票回购、限售股解禁、大宗交易、股票开户数据（旧）、股东增减持、中央结算系统持股明细、股票开盘集合竞价数据、股票收盘集合竞价数据、神奇九转指标、AH股比价、融资融券标的（盘前）、转融资交易汇总、个股资金流向、个股资金流向（THS）、板块资金流向（THS)、行业资金流向（THS）、板块资金流向（DC）、大盘资金流向（DC）、龙虎榜每日统计单、龙虎榜机构交易单、同花顺涨跌停榜单、涨跌停和炸板数据、涨停股票连板天梯、涨停最强板块统计、同花顺行业概念板块、同花顺概念和行业指数行情、同花顺行业概念成分、东方财富概念板块、东方财富概念成分、东财概念和行业指数行情、开盘竞价成交（当日）、市场游资最全名录、游资交易每日明细、同花顺App热榜数、东方财富App热榜、通达信板块信息、通达信板块成分、通达信板块行情、榜单数据（开盘啦）、题材成分（开盘啦）

### 6.2 ETF 专题（6 个）

ETF基本信息、ETF基准指数、ETF实时日线、ETF日线行情、ETF复权因子、ETF份额规模

### 6.3 指数专题（7 个）

指数实时日线、指数周线行情、指数月线行情、申万实时行情、国际主要指数、沪深市场每日交易统计、深圳市场每日交易情况

### 6.4 公募基金（7 个）

基金列表、基金管理人、基金经理、基金规模、基金净值、基金分红、基金持仓

### 6.5 期货数据（11 个）

合约信息、交易日历、日线行情、期货周/月线行情(每日更新)、仓单日报、每日结算参数、每日持仓排名、南华期货指数行情、期货主力与连续合约、期货主要品种交易周报、期货合约涨跌停价格

### 6.6 现货数据（2 个）

上海黄金基础信息、上海黄金现货日行情

### 6.7 期权数据（2 个）

期权合约信息、期权日线行情

### 6.8 债券专题（14 个）

可转债基础信息、可转债发行、可转债赎回信息、可转债票面利率、可转债行情、可转债转股价变动、可转债转股结果、债券回购日行情、柜台流通式债券报价、柜台流通式债券最优报价、大宗交易、大宗交易明细、国债收益率曲线、全球财经事件

### 6.9 外汇数据（2 个）

外汇基础信息（海外）、外汇日线行情

### 6.10 行业经济（8 个）

台湾电子产业月营收、台湾电子产业月营收明细、电影月度票房、电影周度票房、电影日度票房、影院日度票房、全国电影剧本备案数据、全国电视剧备案公示数据

### 6.11 宏观经济（18 个）

Shibor利率、Shibor报价数据、LPR贷款基础利率、Libor利率、Hibor利率、温州民间借贷利率、广州民间借贷利率、国内生产总值（GDP）、居民消费价格指数（CPI）、工业生产者出厂价格指数（PPI）、货币供应量（月）、社融增量（月度）、采购经理指数（PMI）、国债收益率曲线利率、国债实际收益率曲线利率、短期国债利率、国债长期利率、国债长期利率平均值

### 6.12 财富管理（2 个）

各渠道公募基金销售保有规模占比、销售机构公募基金销售保有规模

## 7. 结论

- 如果只看这份 `5000 积分可用接口` 清单，当前仓库已经接入了 `29 / 179` 个接口，其中 `28` 个已经形成本地数据集，`1` 个只做了按需调用。
- 已经接入的部分，核心研究链路其实已经具备：
  - A 股基础列表与交易日历
  - 日线行情 / 复权因子 / 每日指标 / 涨跌停价
  - 停复牌、财务三表、财务指标
  - 分红送股原始数据
  - 股东人数、前十大股东、前十大流通股东
  - 融资融券汇总与明细
  - 指数基础字典与 10 个核心指数日线
  - 申万 / 中信行业字典、成分、日行情
  - 市场指数每日指标
  - 一部分特色数据与资金流数据
- 当前 `index_daily` 首轮只同步了 10 个核心指数白名单：
  - `000001.SH`、`399001.SZ`、`399006.SZ`、`000300.SH`、`000905.SH`
  - `000852.SH`、`000016.SH`、`399005.SZ`、`000688.SH`、`000015.SH`
- 后续待办已经明确：
  - 在验证使用价值和同步成本后，把 `index_daily` 白名单从 10 个继续扩到 20 个或更大的指数集合
- 但从“数据质量”角度，当前阶段最需要做的已经不是继续处理红灯，而是：
  - 维护好现有审计规则
  - 把审计流程定期化
  - 在后续新增数据源时，把它们纳入同一套完整性治理框架
