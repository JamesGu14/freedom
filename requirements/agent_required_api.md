# Freedom Platform — AI Skill 对接 API 设计文档

> 版本：v1.0 | 日期：2026-03-03
> 目标：为 Claude Code 各 AI 股票分析 skill 提供稳定的数据接口，替代不稳定的第三方爬取源（AKShare/Eastmoney）

---

## 总览

### 数据匹配分析

| 数据类型 | Freedom现有 | 需新增同步 | 使用的Skills |
|---------|-----------|-----------|------------|
| 股票基础信息 | ✅ `stock_basic` | — | 全部 |
| 日线行情（OHLCV） | ✅ Parquet `daily/` | — | quant-factor-screener, china-stock-analysis |
| 日度估值（PE/PB/市值） | ✅ Parquet `daily_basic/` | — | undervalued-screener, high-dividend, small-cap |
| 技术指标（均线/MACD等） | ✅ Parquet `indicators/` | — | china-stock-analysis |
| 涨跌停价 | ✅ Parquet `daily_limit/` | — | quant-factor-screener |
| 复权因子 | ✅ DuckDB `adj_factor` | — | 价格复权计算 |
| 申万行业字典+成分 | ✅ MongoDB | — | quant-factor-screener, sector-rotation |
| 申万行业日行情 | ✅ MongoDB `shenwan_daily` | — | sector-rotation-detector |
| 中信行业字典+成分 | ✅ MongoDB | — | sector-rotation-detector |
| 中信行业日行情 | ✅ MongoDB `citic_daily` | — | sector-rotation-detector |
| 大盘指数估值+技术因子 | ✅ MongoDB | — | sector-rotation-detector |
| 交易日历 | ✅ MongoDB | — | 全部 |
| **财务报表数据** | ❌ 缺失 | ⭐P0新增 | financial-statement-analyzer, quant-factor |
| **关键财务指标** | ❌ 缺失 | ⭐P0新增 | 几乎全部 |
| **股息历史** | ❌ 缺失 | ⭐P0新增 | high-dividend-strategy |
| **董监高增减持** | ❌ 缺失 | ⭐P1新增 | insider-trading-analyzer |
| **宏观数据** | ❌ 缺失 | ⭐P1新增 | sector-rotation-detector |
| **公司公告/事件** | ❌ 缺失 | P2新增 | event-driven-detector |

---

## API 规范说明

- **Base URL**: `https://your-freedom-host/api/v1`
- **认证**: `Authorization: Bearer <jwt_token>`
- **日期格式**: `YYYYMMDD`（与 Tushare 保持一致）
- **股票代码**: `ts_code` 格式，如 `000001.SZ`、`600000.SH`
- **分页**: 大结果集使用 `?page=1&page_size=100`
- **错误格式**:
```json
{ "code": 400, "message": "参数错误描述", "data": null }
```

---

## Part A — 可立即开发（Freedom 已有数据）

### A1. 股票基础信息

#### `GET /stocks/basic`

获取全量或筛选后的股票基础信息列表。

**Query Parameters**

| 参数 | 类型 | 必填 | 说明 |
|-----|------|-----|------|
| `market` | string | 否 | 市场筛选：`MAIN`主板 / `GEM`创业板 / `STAR`科创板 |
| `exchange` | string | 否 | 交易所：`SSE`上交所 / `SZSE`深交所 |
| `ts_codes` | string | 否 | 逗号分隔，批量查询，如 `000001.SZ,600000.SH` |

**Response**
```json
{
  "code": 200,
  "data": [
    {
      "ts_code": "000001.SZ",
      "symbol": "000001",
      "name": "平安银行",
      "industry": "银行",
      "market": "主板",
      "exchange": "SZSE",
      "list_date": "19910403",
      "is_hs": "S"
    }
  ],
  "total": 5000
}
```

**使用 Skills**: 全部
**优先级**: P0

---

#### `GET /stocks/basic/{ts_code}`

获取单只股票基础信息。

**Response**: 同上，返回单条记录。

---

#### `GET /stocks/search`

按名称或代码搜索股票。

**Query Parameters**

| 参数 | 类型 | 必填 | 说明 |
|-----|------|-----|------|
| `q` | string | 是 | 搜索关键词，匹配代码或名称 |
| `limit` | int | 否 | 返回条数，默认20 |

**Response**: 返回匹配的股票列表（同 `/stocks/basic` 格式）

---

### A2. 日线行情

#### `GET /stocks/{ts_code}/daily`

获取单只股票日线行情（前复权或不复权）。

**Query Parameters**

| 参数 | 类型 | 必填 | 说明 |
|-----|------|-----|------|
| `start_date` | string | 否 | 开始日期，如 `20250101` |
| `end_date` | string | 否 | 结束日期，默认最新 |
| `adj` | string | 否 | 复权类型：`qfq`前复权 / `hfq`后复权 / `none`不复权（默认） |
| `fields` | string | 否 | 指定返回字段，逗号分隔 |

**Response**
```json
{
  "code": 200,
  "data": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260303",
      "open": 12.50,
      "high": 12.80,
      "low": 12.30,
      "close": 12.60,
      "pre_close": 12.45,
      "change": 0.15,
      "pct_chg": 1.20,
      "vol": 1234567,
      "amount": 15678900.0
    }
  ]
}
```

**使用 Skills**: quant-factor-screener, china-stock-analysis
**优先级**: P0

---

#### `POST /stocks/daily/batch`

批量获取多只股票指定日期的行情（横截面数据，适合选股）。

**Request Body**
```json
{
  "ts_codes": ["000001.SZ", "600000.SH", "300750.SZ"],
  "trade_date": "20260303",
  "adj": "qfq"
}
```

**Response**: 返回多只股票当日行情列表。

**使用 Skills**: quant-factor-screener（多只同时拉取动量数据）
**优先级**: P0

---

#### `GET /stocks/{ts_code}/daily/recent`

获取最近 N 个交易日行情（用于计算动量因子）。

**Query Parameters**

| 参数 | 类型 | 必填 | 说明 |
|-----|------|-----|------|
| `n` | int | 是 | 最近 N 个交易日，如 `5`/`20`/`250` |
| `adj` | string | 否 | 复权类型，默认 `qfq` |

**Response**: 返回最近 N 条日线数据。

---

#### `POST /stocks/daily/stats/screen`

按交易日区间对全 A 股或指定股票池做批量日线行为统计，并直接返回满足条件的股票列表。

**Request Body**

| 字段 | 类型 | 必填 | 说明 |
|-----|------|-----|------|
| `start_date` | string | 否 | 开始日期，支持 `YYYYMMDD` / `YYYY-MM-DD` |
| `end_date` | string | 否 | 结束日期；不传时默认最新交易日 |
| `lookback_days` | int | 否 | 最近 N 个交易日；若同时传 `start_date/end_date`，则忽略 |
| `universe` | string | 否 | 股票池：`all_a` / `main_board` / `chi_next` / `star`，默认 `all_a` |
| `ts_codes` | string[] | 否 | 指定股票列表；若传入，则优先作为基础集合 |
| `industry_source` | string | 否 | 行业来源：`sw` / `citic` |
| `industry_codes` | string[] | 否 | 行业代码列表；在基础股票池上继续过滤 |
| `up_days_gte` | int | 否 | 上涨天数下限 |
| `pct_change_gte` | float | 否 | 区间总涨跌幅下限（%） |
| `max_up_streak_gte` | int | 否 | 最大连续上涨天数下限 |
| `avg_amount_gte` | float | 否 | 区间日均成交额下限 |
| `exclude_st` | bool | 否 | 是否排除 `ST/*ST` |
| `exclude_suspended` | bool | 否 | 是否排除区间内有效交易日不足的股票 |
| `sort_by` | string | 否 | 排序字段：`up_days` / `pct_change` / `max_up_streak` / `avg_amount` |
| `sort_order` | string | 否 | 排序方向：`asc` / `desc` |
| `page` | int | 否 | 页码，默认 `1` |
| `page_size` | int | 否 | 每页条数，默认 `100` |

**统计口径**

- `trade_days`：区间内有效交易日数
- `up_days`：`close > pre_close` 的天数
- `down_days`：`close < pre_close` 的天数
- `flat_days`：`close == pre_close` 的天数
- `pct_change`：`(最后一个交易日 close / 第一个交易日 pre_close - 1) * 100`
- `max_up_streak`：区间内最大连续上涨天数
- `max_down_streak`：区间内最大连续下跌天数
- `avg_amount`：区间内日均成交额
- `latest_close`：区间最后一个交易日收盘价
- `latest_pct_chg`：区间最后一个交易日涨跌幅，优先使用原始 `pct_chg`，缺失时回退 `(close - pre_close) / pre_close * 100`

**示例请求**
```json
{
  "lookback_days": 10,
  "universe": "all_a",
  "up_days_gte": 8,
  "exclude_st": true,
  "exclude_suspended": true,
  "sort_by": "up_days",
  "sort_order": "desc",
  "page": 1,
  "page_size": 100
}
```

**示例响应**
```json
{
  "code": 200,
  "data": [
    {
      "ts_code": "000001.SZ",
      "name": "平安银行",
      "start_date": "20260220",
      "end_date": "20260306",
      "trade_days": 10,
      "up_days": 8,
      "down_days": 2,
      "flat_days": 0,
      "pct_change": 7.35,
      "max_up_streak": 4,
      "max_down_streak": 1,
      "avg_amount": 1234567890.12,
      "latest_close": 12.34,
      "latest_pct_chg": 1.52
    }
  ],
  "total": 123,
  "page": 1,
  "page_size": 100
}
```

**Response**: 返回已聚合好的统计结果，不返回原始 K 线明细。

**使用 Skills**: quant-factor-screener, china-stock-analysis
**优先级**: P0

---

### A3. 日度估值与基本面指标

#### `GET /stocks/{ts_code}/daily-basic`

获取单只股票的日度估值与基本面指标（PE/PB/市值/换手率等）。

**Query Parameters**

| 参数 | 类型 | 必填 | 说明 |
|-----|------|-----|------|
| `start_date` | string | 否 | 开始日期 |
| `end_date` | string | 否 | 结束日期 |

**Response**
```json
{
  "code": 200,
  "data": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260303",
      "close": 12.60,
      "turnover_rate": 0.85,
      "turnover_rate_f": 1.20,
      "volume_ratio": 1.05,
      "pe": 8.5,
      "pe_ttm": 8.2,
      "pb": 0.85,
      "ps": 1.20,
      "ps_ttm": 1.18,
      "dv_ratio": 4.5,
      "dv_ttm": 4.3,
      "total_share": 19405918.0,
      "float_share": 17520000.0,
      "free_share": 15200000.0,
      "total_mv": 244714000.0,
      "circ_mv": 220752000.0
    }
  ]
}
```

**使用 Skills**: undervalued-stock-screener, high-dividend-strategy, small-cap-growth-identifier, quant-factor-screener
**优先级**: P0

---

#### `GET /stocks/daily-basic/snapshot`

获取全市场最新交易日的估值快照（选股核心接口）。

**Query Parameters**

| 参数 | 类型 | 必填 | 说明 |
|-----|------|-----|------|
| `trade_date` | string | 否 | 指定日期，默认最新交易日 |
| `pe_ttm_max` | float | 否 | PE(TTM)上限筛选 |
| `pb_max` | float | 否 | PB上限筛选 |
| `total_mv_min` | float | 否 | 总市值下限（万元） |
| `total_mv_max` | float | 否 | 总市值上限（万元） |
| `dv_ratio_min` | float | 否 | 股息率下限（%） |
| `turnover_rate_max` | float | 否 | 换手率上限（%），低换手筛选 |
| `page` | int | 否 | 页码，默认1 |
| `page_size` | int | 否 | 每页条数，默认500 |

**Response**: 返回全市场（或筛选后）最新估值快照列表。

**使用 Skills**: undervalued-stock-screener（低PE/PB筛选）、small-cap-growth-identifier（小市值）、quant-factor-screener（低换手因子）
**优先级**: P0（选股最常用接口）

---

### A4. 技术指标

#### `GET /stocks/{ts_code}/indicators`

获取单只股票计算好的技术指标。

**Query Parameters**

| 参数 | 类型 | 必填 | 说明 |
|-----|------|-----|------|
| `start_date` | string | 否 | 开始日期 |
| `end_date` | string | 否 | 结束日期 |
| `fields` | string | 否 | 指定返回指标，如 `ma20,macd,rsi12` |

**Response**
```json
{
  "code": 200,
  "data": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260303",
      "close_qfq": 12.60,
      "ma5": 12.30, "ma10": 12.10, "ma20": 11.90,
      "ma30": 11.60, "ma60": 11.20, "ma90": 10.80, "ma250": 10.50,
      "macd": 0.15, "macd_signal": 0.12, "macd_hist": 0.03,
      "kdj_k": 72.5, "kdj_d": 68.3, "kdj_j": 80.9,
      "rsi6": 65.2, "rsi12": 60.8, "rsi24": 58.3,
      "boll_upper": 13.20, "boll_middle": 12.10, "boll_lower": 11.00,
      "atr": 0.35, "cci": 80.5,
      "updays": 3, "downdays": 0,
      "pe_ttm": 8.2, "pb": 0.85,
      "turnover_rate": 0.85, "volume_ratio": 1.05
    }
  ]
}
```

**使用 Skills**: china-stock-analysis（技术面分析）
**优先级**: P1

---

### A5. 申万行业体系

#### `GET /industry/shenwan/tree`

获取申万行业层级树（一、二、三级）。

**Query Parameters**

| 参数 | 类型 | 必填 | 说明 |
|-----|------|-----|------|
| `level` | int | 否 | 层级，1/2/3，不传返回全部 |
| `version` | string | 否 | 申万版本，默认最新 |

**Response**
```json
{
  "code": 200,
  "data": [
    {
      "industry_code": "801010",
      "industry_name": "农林牧渔",
      "index_code": "801010.SI",
      "level": 1,
      "parent_code": null,
      "children": [
        {
          "industry_code": "801011",
          "industry_name": "种植业",
          "level": 2,
          "parent_code": "801010"
        }
      ]
    }
  ]
}
```

**使用 Skills**: quant-factor-screener（行业内排名）、sector-rotation-detector（行业配置）
**优先级**: P0

---

#### `GET /industry/shenwan/members`

查询申万行业成分股。

**Query Parameters**

| 参数 | 类型 | 必填 | 说明 |
|-----|------|-----|------|
| `industry_code` | string | 条件必填 | 行业代码 |
| `level` | int | 否 | 层级，默认2 |
| `is_new` | bool | 否 | 只返回当前成分，默认 `true` |
| `ts_code` | string | 条件必填 | 反查：查询某股票所属行业 |

**Response**
```json
{
  "code": 200,
  "data": [
    {
      "ts_code": "000001.SZ",
      "name": "平安银行",
      "l1_code": "801780",
      "l1_name": "银行",
      "l2_code": "801781",
      "l2_name": "国有大型银行II",
      "l3_code": null,
      "in_date": "20231201",
      "is_new": true
    }
  ]
}
```

**使用 Skills**: quant-factor-screener（核心：按行业找成分股）、china-stock-analysis
**优先级**: P0（这个是之前 akshare 里 broken 的核心数据）

---

#### `GET /industry/shenwan/daily`

获取申万行业指数日行情与涨跌排名。

**Query Parameters**

| 参数 | 类型 | 必填 | 说明 |
|-----|------|-----|------|
| `trade_date` | string | 否 | 指定日期，默认最新 |
| `start_date` | string | 否 | 日期范围查询 |
| `end_date` | string | 否 | 日期范围查询 |
| `level` | int | 否 | 层级 1/2，默认1 |
| `industry_code` | string | 否 | 特定行业代码 |
| `order_by` | string | 否 | 排序字段：`pct_change`/`rank`，默认按排名 |

**Response**
```json
{
  "code": 200,
  "data": [
    {
      "ts_code": "801780.SI",
      "trade_date": "20260303",
      "name": "银行",
      "level": 1,
      "close": 1250.50,
      "pct_change": 1.85,
      "vol": 98765432,
      "amount": 12345678900.0,
      "rank": 1,
      "rank_total": 31
    }
  ]
}
```

**使用 Skills**: sector-rotation-detector（行业强弱排名）、quant-factor-screener（近5日强势行业）
**优先级**: P0

---

#### `GET /industry/shenwan/daily/ranking`

获取指定日期的申万一级行业涨跌幅排行榜（专为行业轮动分析优化）。

**Query Parameters**

| 参数 | 类型 | 必填 | 说明 |
|-----|------|-----|------|
| `trade_date` | string | 否 | 默认最新交易日 |
| `period` | string | 否 | 区间涨幅统计：`1d`/`5d`/`10d`/`20d`/`60d` |

**Response**: 返回按期间涨幅排序的行业列表，含涨跌幅、成交量、排名变化。

**使用 Skills**: sector-rotation-detector、quant-factor-screener（5日强势行业筛选）
**优先级**: P0

---

### A6. 中信行业体系

#### `GET /industry/citic/tree`

获取中信行业层级树。与申万接口结构相同，不再赘述。

#### `GET /industry/citic/members`

查询中信行业成分股。参数同申万接口，`industry_code` 为中信行业代码。

#### `GET /industry/citic/daily`

获取中信行业指数日行情与排名。结构同申万接口。

**优先级**: P1

---

### A7. 大盘指数

#### `GET /market-index/daily-basic`

获取主要大盘指数（上证、深证、沪深300、中证500等）的估值与市值指标。

**Query Parameters**

| 参数 | 类型 | 必填 | 说明 |
|-----|------|-----|------|
| `ts_codes` | string | 否 | 指定指数代码，如 `000001.SH,399001.SZ,000300.SH` |
| `trade_date` | string | 否 | 指定日期 |
| `start_date` | string | 否 | 日期范围 |
| `end_date` | string | 否 | 日期范围 |

**Response**
```json
{
  "code": 200,
  "data": [
    {
      "ts_code": "000300.SH",
      "trade_date": "20260303",
      "total_mv": 598765432100.0,
      "float_mv": 450000000000.0,
      "pe": 13.5,
      "pb": 1.45,
      "turnover_rate": 0.95,
      "turnover_rate_f": 1.25
    }
  ]
}
```

**使用 Skills**: sector-rotation-detector（大盘估值水平判断）
**优先级**: P1

---

#### `GET /market-index/factors`

获取指数技术因子（均线、MACD、KDJ、RSI等）。

**Query Parameters**: `ts_code`, `start_date`, `end_date`, `source`（`market`/`sw`/`ci`）

**使用 Skills**: sector-rotation-detector（趋势判断）
**优先级**: P1

---

### A8. 交易日历

#### `GET /trade-calendar`

查询交易日历。

**Query Parameters**

| 参数 | 类型 | 必填 | 说明 |
|-----|------|-----|------|
| `exchange` | string | 否 | `SSE`/`SZSE`，默认 `SSE` |
| `start_date` | string | 是 | 开始日期 |
| `end_date` | string | 是 | 结束日期 |
| `is_open` | bool | 否 | 只返回交易日 `true` 或非交易日 `false` |

**Response**
```json
{
  "code": 200,
  "data": [
    { "cal_date": "20260303", "is_open": 1 },
    { "cal_date": "20260304", "is_open": 1 },
    { "cal_date": "20260307", "is_open": 0 }
  ]
}
```

**使用 Skills**: 全部（计算动量因子的交易日数需要）
**优先级**: P0

---

#### `GET /trade-calendar/latest-trade-date`

获取最近的交易日（用于 "最新" 查询的日期锚点）。

**Response**
```json
{ "code": 200, "data": { "trade_date": "20260303" } }
```

---

### A9. 涨跌停价

#### `GET /stocks/{ts_code}/limit-prices`

获取个股涨跌停价历史（用于判断是否曾触发涨停/一字板）。

**Query Parameters**: `start_date`, `end_date`

**Response**
```json
{
  "code": 200,
  "data": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260303",
      "pre_close": 12.45,
      "up_limit": 13.70,
      "down_limit": 11.21
    }
  ]
}
```

**使用 Skills**: quant-factor-screener（排除连板股票）
**优先级**: P1

---

#### `GET /stocks/limit-prices/snapshot`

获取全市场当日涨跌停价快照。

**优先级**: P1

---

## Part B — 建议新增 Tushare 同步后开发

> 以下数据在 Freedom 中尚未落地，但 Tushare Pro 均有对应接口。建议按优先级顺序新增同步脚本，然后开发 API。

---

### B1. 财务指标（⭐P0 — 几乎所有 Skills 都需要）

#### 新增同步
- Tushare 接口：`fina_indicator`（财务指标汇总）、`income`、`balancesheet`、`cashflow`
- 建议同步频率：每季报后全量更新（3/4/8/10月）
- 建议存储：MongoDB collection `financial_indicators` + `income_statement` + `balance_sheet` + `cashflow`

#### `GET /stocks/{ts_code}/financials/indicators`

获取关键财务指标（最常用，单接口覆盖大多数 skill 需求）。

**Query Parameters**

| 参数 | 类型 | 必填 | 说明 |
|-----|------|-----|------|
| `period` | string | 否 | 报告期，如 `20250930`，默认最新 |
| `period_type` | string | 否 | `annual`年报 / `quarterly`季报，默认季报 |
| `limit` | int | 否 | 返回最近 N 期，默认8（2年） |

**Response**
```json
{
  "code": 200,
  "data": [
    {
      "ts_code": "000001.SZ",
      "ann_date": "20251031",
      "end_date": "20250930",
      "roe": 12.5,
      "roe_yoy": 0.8,
      "roa": 1.1,
      "netprofit_margin": 28.5,
      "grossprofit_margin": 35.2,
      "debt_to_assets": 91.2,
      "current_ratio": 1.05,
      "quick_ratio": 0.95,
      "revenue": 47823000000.0,
      "revenue_yoy": 8.5,
      "n_income": 13623000000.0,
      "n_income_yoy": 12.3,
      "fcf": 8900000000.0,
      "eps": 0.68,
      "bps": 5.45
    }
  ]
}
```

**使用 Skills**: quant-factor-screener, china-stock-analysis, financial-statement-analyzer, high-dividend-strategy, undervalued-stock-screener, small-cap-growth-identifier
**优先级**: P0 — 最高优先级，新增后覆盖面最广

---

#### `GET /stocks/{ts_code}/financials/income`

获取利润表（详细版）。

**Response** 含：营业收入、营业成本、毛利、研发费用、管理费用、营业利润、净利润、少数股东权益等，支持多期查询。

---

#### `GET /stocks/{ts_code}/financials/balance`

获取资产负债表。

**Response** 含：货币资金、应收账款、存货、固定资产、商誉、总资产、总负债、有息负债、股东权益等。

---

#### `GET /stocks/{ts_code}/financials/cashflow`

获取现金流量表。

**Response** 含：经营性现金流、投资性现金流、筹资性现金流、自由现金流（FCF）等。

---

#### `POST /stocks/financials/indicators/batch`

批量获取多只股票最新财务指标快照（选股接口）。

**Request Body**
```json
{
  "ts_codes": ["000001.SZ", "600000.SH"],
  "period": "20250930",
  "fields": ["roe", "revenue_yoy", "n_income_yoy", "debt_to_assets", "fcf"]
}
```

**使用 Skills**: undervalued-stock-screener, small-cap-growth-identifier, quant-factor-screener
**优先级**: P0

---

#### `GET /stocks/financials/indicators/screen`

财务指标筛选接口（选股核心）。

**Query Parameters**

| 参数 | 类型 | 说明 |
|-----|------|------|
| `period` | string | 报告期，默认最新 |
| `roe_min` | float | ROE 下限（%） |
| `revenue_yoy_min` | float | 营收增速下限（%） |
| `n_income_yoy_min` | float | 净利增速下限（%） |
| `debt_to_assets_max` | float | 负债率上限（%） |
| `netprofit_margin_min` | float | 净利率下限（%） |
| `fcf_positive` | bool | 是否要求FCF为正 |
| `page` / `page_size` | int | 分页 |

**使用 Skills**: quant-factor-screener（Quality因子筛选）、undervalued-stock-screener
**优先级**: P0

---

### B2. 股息历史（⭐P0 — high-dividend-strategy 核心）

#### 新增同步
- Tushare 接口：`dividend`（分红方案）
- 建议存储：MongoDB collection `dividend_history`

#### `GET /stocks/{ts_code}/dividends`

获取股票历史分红记录。

**Response**
```json
{
  "code": 200,
  "data": [
    {
      "ts_code": "000001.SZ",
      "end_date": "20241231",
      "ann_date": "20250310",
      "ex_date": "20250428",
      "div_proc": "实施",
      "cash_div": 2.80,
      "cash_div_tax": 2.52,
      "record_date": "20250427",
      "pay_date": "20250428",
      "div_listdate": "20250429",
      "imp_ann_date": "20250310"
    }
  ]
}
```

#### `GET /stocks/{ts_code}/dividends/summary`

获取股票分红汇总（近5年）。

**Response**
```json
{
  "code": 200,
  "data": {
    "ts_code": "000001.SZ",
    "consecutive_years": 12,
    "avg_dv_ratio_5y": 4.2,
    "dividend_cagr_5y": 8.5,
    "total_cash_div_5y": 12.50,
    "latest_dv_ratio": 4.8,
    "payout_ratio": 32.5
  }
}
```

**使用 Skills**: high-dividend-strategy
**优先级**: P0

---

#### `GET /stocks/dividends/screen`

高股息筛选接口。

**Query Parameters**: `dv_ratio_min`、`consecutive_years_min`、`payout_ratio_max`、`total_mv_min`

**使用 Skills**: high-dividend-strategy
**优先级**: P0

---

### B3. 董监高增减持（⭐P1 — insider-trading-analyzer）

#### 新增同步
- Tushare 接口：`stk_holdertrade`（股东增减持）
- 建议存储：MongoDB collection `insider_trades`

#### `GET /stocks/{ts_code}/insider-trades`

获取个股董监高及大股东增减持记录。

**Query Parameters**

| 参数 | 类型 | 说明 |
|-----|------|------|
| `start_date` | string | 开始日期 |
| `end_date` | string | 结束日期 |
| `holder_type` | string | `P`个人 / `C`公司 / `G`高管 |
| `trade_type` | string | `IN`增持 / `DE`减持 |

**Response**
```json
{
  "code": 200,
  "data": [
    {
      "ts_code": "000001.SZ",
      "ann_date": "20260215",
      "holder_name": "张三",
      "holder_type": "G",
      "in_de": "IN",
      "change_vol": 500000,
      "change_ratio": 0.26,
      "after_share": 19500000,
      "after_ratio": 10.05,
      "avg_price": 12.30,
      "total_share": 194059180,
      "begin_date": "20260210",
      "close_date": "20260215"
    }
  ]
}
```

#### `GET /market/insider-trades/latest`

获取全市场最新增减持动态（按信号强度排序）。

**Query Parameters**: `trade_type`、`days`（最近N天）、`min_amount`（最小交易金额）

**使用 Skills**: insider-trading-analyzer
**优先级**: P1

---

### B4. 宏观经济数据（⭐P1 — sector-rotation-detector）

#### 新增同步
- Tushare 接口：`shibor`、`hibor` 或直接用现有 akshare macro API
- 建议存储：MongoDB collection `macro_indicators`

#### `GET /macro/money-supply`

获取 M0/M1/M2 货币供应量。

**Response**
```json
{
  "code": 200,
  "data": [
    {
      "month": "202601",
      "m0": 116543.2,
      "m0_yoy": 11.2,
      "m1": 115678.3,
      "m1_yoy": 4.9,
      "m2": 3135432.1,
      "m2_yoy": 9.0
    }
  ]
}
```

#### `GET /macro/lpr`

获取 LPR 利率历史。

**Response**
```json
{
  "code": 200,
  "data": [
    {
      "date": "20260120",
      "lpr_1y": 3.00,
      "lpr_5y": 3.50
    }
  ]
}
```

#### `GET /macro/pmi`

获取官方制造业 PMI 数据。

#### `GET /macro/cpi-ppi`

获取 CPI/PPI 月度数据。

#### `GET /macro/social-financing`

获取社会融资规模数据。

**使用 Skills**: sector-rotation-detector
**优先级**: P1

---

### B5. 公司事件与公告（P2 — event-driven-detector）

#### 新增同步（可后续规划）
- Tushare 接口：`repurchase`（回购）、`major_news`、`anns`（公告）
- 建议存储：MongoDB collection `corporate_events`

#### `GET /stocks/{ts_code}/events/buyback`

获取股票回购计划与进度。

#### `GET /market/events/ma-restructure`

获取近期并购重组公告列表。

#### `GET /stocks/{ts_code}/events/holder-changes`

获取股东增减持及质押事件。

**使用 Skills**: event-driven-detector
**优先级**: P2

---

## 开发优先级汇总

### P0 — 立即可开发（Freedom已有数据）

| 接口 | 数据来源 | 覆盖Skills |
|-----|---------|-----------|
| `GET /stocks/basic` | MongoDB `stock_basic` | 全部 |
| `GET /stocks/{ts_code}/daily` | Parquet `daily/` | quant-factor-screener, china-stock-analysis |
| `GET /stocks/daily/snapshot` | Parquet `daily/` | quant-factor-screener |
| `POST /stocks/daily/stats/screen` | Parquet `daily/` + MongoDB `stock_basic/trade_calendar` | quant-factor-screener, china-stock-analysis |
| `GET /stocks/daily-basic/snapshot` | Parquet `daily_basic/` | undervalued-screener, high-dividend, small-cap |
| `GET /industry/shenwan/members` | MongoDB `shenwan_industry_member` | quant-factor-screener |
| `GET /industry/shenwan/daily/ranking` | MongoDB `shenwan_daily` | sector-rotation, quant-factor |
| `GET /trade-calendar/latest-trade-date` | MongoDB `trade_calendar` | 全部 |

### P0 — 需新增Tushare同步（高价值）

| 接口 | Tushare接口 | 覆盖Skills |
|-----|------------|-----------|
| `GET /stocks/{ts_code}/financials/indicators` | `fina_indicator` | 6个skills |
| `GET /stocks/financials/indicators/screen` | `fina_indicator` | undervalued-screener, quant-factor |
| `GET /stocks/{ts_code}/dividends` | `dividend` | high-dividend-strategy |
| `GET /stocks/dividends/screen` | `dividend` | high-dividend-strategy |

### P1 — 需新增Tushare同步（中等价值）

| 接口 | Tushare接口 | 覆盖Skills |
|-----|------------|-----------|
| `GET /stocks/{ts_code}/insider-trades` | `stk_holdertrade` | insider-trading-analyzer |
| `GET /market/insider-trades/latest` | `stk_holdertrade` | insider-trading-analyzer |
| `GET /macro/money-supply` | `cn_m` | sector-rotation-detector |
| `GET /macro/lpr` | `shibor_lpr` | sector-rotation-detector |
| `GET /macro/pmi` | `cn_pmi` | sector-rotation-detector |
| `GET /stocks/{ts_code}/indicators` | Parquet `indicators/` | china-stock-analysis |

### P2 — 可规划（事件驱动类）

| 接口 | Tushare接口 | 覆盖Skills |
|-----|------------|-----------|
| 回购/增减持/并购事件类接口 | `repurchase`,`major_news` | event-driven-detector |

---

## 附录：接口与 Skills 对应关系矩阵

| API 接口 | quant-factor | sector-rotation | china-stock | financial-stmt | high-dividend | undervalued | insider-trade | small-cap | event-driven |
|---------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `/stocks/basic` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `/stocks/{ts}/daily` | ✅ | — | ✅ | — | — | — | — | — | — |
| `/stocks/daily/stats/screen` | ✅ | ✅ | ✅ | — | — | — | — | ✅ | — |
| `/stocks/daily-basic/snapshot` | ✅ | — | ✅ | — | ✅ | ✅ | — | ✅ | — |
| `/industry/shenwan/members` | ✅ | ✅ | ✅ | — | — | — | — | — | — |
| `/industry/shenwan/daily/ranking` | ✅ | ✅ | — | — | — | — | — | — | — |
| `/stocks/{ts}/financials/indicators` | ✅ | — | ✅ | ✅ | ✅ | ✅ | — | ✅ | — |
| `/stocks/financials/screen` | ✅ | — | — | — | — | ✅ | — | ✅ | — |
| `/stocks/{ts}/dividends` | — | — | ✅ | — | ✅ | — | — | — | — |
| `/market/insider-trades/latest` | — | — | — | — | — | — | ✅ | — | ✅ |
| `/macro/money-supply` | — | ✅ | — | — | — | — | — | — | — |
| `/macro/lpr` | — | ✅ | — | — | — | — | — | — | — |
| `/stocks/{ts}/indicators` | — | — | ✅ | — | — | — | — | — | — |
| `/market-index/daily-basic` | — | ✅ | — | — | — | — | — | — | — |

---

*文档生成时间：2026-03-03 | 基于 Freedom 数据库扫描结果 + 各 Skill 数据需求分析*
