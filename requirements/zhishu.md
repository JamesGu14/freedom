# 指数数据（中信板块 + 大盘指数）需求设计

## 1. 目标与范围

本需求覆盖三类数据：

1. 中信行业成分与行业指数日行情（`ci_index_member` + `ci_daily`）。
2. 大盘指数每日指标（`index_dailybasic`）。
3. 指数技术面因子（`idx_factor_pro`）。

本阶段只做设计，不做代码开发。设计目标是：

- 明确 TuShare 接口的输入/输出格式。
- 设计可落库的数据结构（MongoDB）。
- 设计 `backend/scripts/daily/` 下统一同步脚本能力（`--start-date`/`--end-date` + 冷启动全量）。
- 规划前端“申万板块排名/中信板块排名”和“大盘指数”页面形态。

---

## 2. TuShare 接口格式分析

### 2.1 `ci_index_member`（doc_id=373）

用途：中信行业成分股（L1/L2/L3）。

输入参数：

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| index_code | str | N | 行业指数代码，例如 `CI005001.WI` |
| level | str | N | 行业级别，`L1`/`L2`/`L3` |
| ts_code | str | N | 股票代码 |
| is_new | str | N | 是否最新（`Y`/`N`） |

输出字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| index_code | str | 中信行业指数代码 |
| industry_name | str | 中信行业名称 |
| level | str | 行业级别（L1/L2/L3） |
| industry_code | str | 中信行业代码 |
| cons_code | str | 成分股代码（ts_code） |
| cons_ticker | str | 成分股代码（symbol） |
| cons_name | str | 成分股简称 |
| in_date | str | 纳入日期（YYYYMMDD） |
| out_date | str | 剔除日期（YYYYMMDD） |
| is_new | str | 是否最新（Y/N） |

关键点：

- 该接口同时承载行业维表信息（`index_code/industry_name/level`）和成分关系（`cons_code`）。
- 行业层级是字符串（`L1/L2/L3`），入库建议转为整数层级（1/2/3）并保留原值。

### 2.2 `ci_daily`（doc_id=308）

用途：中信行业指数日线行情。

输入参数：

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| ts_code | str | N | 行业代码（如 `CI005001.WI`） |
| trade_date | str | N | 交易日期 |
| start_date | str | N | 开始日期 |
| end_date | str | N | 结束日期 |

输出字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| ts_code | str | 中信行业指数代码 |
| trade_date | str | 交易日期 |
| open | float | 开盘点位 |
| low | float | 最低点位 |
| high | float | 最高点位 |
| close | float | 收盘点位 |
| change | float | 涨跌点位 |
| pct_change | float | 涨跌幅（%） |
| vol | float | 成交量（万股） |
| amount | float | 成交额（万元） |

关键点：

- 返回不带行业名称/层级，需要依赖 `ci_index_member` 维度映射补齐。
- 与申万 `sw_daily` 的结构相近，可复用现有排名计算模型。

### 2.3 `index_dailybasic`（doc_id=128）

用途：获取指数每日估值与换手指标。

输入参数：

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| ts_code | str | N | 指数代码 |
| trade_date | str | N | 交易日期 |
| start_date | str | N | 开始日期 |
| end_date | str | N | 结束日期 |

输出字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| ts_code | str | TS指数代码 |
| trade_date | str | 交易日期 |
| total_mv | float | 当日总市值（亿） |
| float_mv | float | 当日流通市值（亿） |
| total_share | float | 当日总股本（亿） |
| float_share | float | 当日流通股本（亿） |
| free_share | float | 当日自由流通股本（亿） |
| turnover_rate | float | 换手率 |
| turnover_rate_f | float | 换手率（基于自由流通股本） |
| total_pe | float | 市盈率 |
| pe | float | 市盈率TTM |
| pb | float | 市净率 |

### 2.4 `idx_factor_pro`（doc_id=358）

用途：指数技术面因子。

输入参数：

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| ts_code | str | N | 指数代码 |
| trade_date | str | N | 交易日期 |
| start_date | str | N | 开始日期 |
| end_date | str | N | 结束日期 |

输出字段（原样入库）：

- 标识字段：`ts_code`, `trade_date`, `ts_name`, `market`
- 动量/震荡类：`arbr`, `psy`, `brar`, `mtm`, `mass`, `roc`, `cci`, `rsi_6`, `rsi_12`, `rsi_24`, `wr_10`, `wr_6`, `trix_12`, `trix_24`, `trix`, `dpo`, `bias_6`, `bias_12`, `bias_24`, `cmo`, `dx`
- KDJ/MACD/均线：`kdj_k`, `kdj_d`, `kdj_j`, `macd_dif`, `macd_dea`, `macd`, `sma_5`, `sma_10`, `sma_20`, `sma_60`, `ema_5`, `ema_10`, `ema_20`, `ema_60`, `expma_12`, `expma_50`
- 量能类：`vr`, `vr_26`, `mfi_14`, `obv`, `mavol5`, `mavol10`, `mavol20`, `vol_log_return`
- 波动与通道：`emv`, `atr_6`, `atr_14`, `ktn_down`, `ktn_mid`, `ktn_upper`, `up20`, `down20`, `up_20`, `down_20`, `hhv`, `llv`, `up`, `down`, `ht`, `lt`, `ene`
- 趋势与其他：`asi`, `adtm`, `sk`, `sd`, `dmi_pdi`, `dmi_mdi`, `dmi_adx`, `dmi_adxr`, `cr`, `ma_cr`, `dn_rho_10`, `jn_rho_10`, `tei`, `ref_line`, `ref_boll`
- 收益相关：`pct_change`, `simple_return`, `log_return`

关键点：

- 字段很多，且未来可能扩展，建议“按接口原字段直存”，避免字段映射丢失。

---

## 3. 数据库表结构设计（MongoDB）

### 3.1 新建集合：`citic_industry`

用途：中信行业维表（从 `ci_index_member` 去重提取）。

文档示例：

```javascript
{
  "index_code": "CI005001.WI",
  "industry_code": "CI005001",
  "industry_name": "银行",
  "level": 1,
  "level_raw": "L1",
  "source": "citic",
  "is_active": true,
  "member_count_latest": 42,
  "updated_at": ISODate("2026-02-06T10:00:00Z"),
  "created_at": ISODate("2026-02-06T10:00:00Z")
}
```

索引建议：

```javascript
db.citic_industry.createIndex(
  { "index_code": 1 },
  { unique: true, name: "idx_index_code_unique" }
)
db.citic_industry.createIndex(
  { "level": 1, "industry_name": 1 },
  { name: "idx_level_name" }
)
```

### 3.2 新建集合：`citic_industry_member`

用途：中信行业成分历史关系表。

文档示例：

```javascript
{
  "index_code": "CI005001.WI",
  "industry_code": "CI005001",
  "industry_name": "银行",
  "level": 1,
  "level_raw": "L1",
  "cons_code": "600000.SH",
  "cons_ticker": "600000",
  "cons_name": "浦发银行",
  "in_date": "20190101",
  "out_date": null,
  "is_new": "Y",
  "updated_at": ISODate("2026-02-06T10:00:00Z"),
  "created_at": ISODate("2026-02-06T10:00:00Z")
}
```

索引建议：

```javascript
db.citic_industry_member.createIndex(
  { "cons_code": 1, "index_code": 1, "in_date": 1 },
  { unique: true, name: "idx_cons_index_indate" }
)
db.citic_industry_member.createIndex(
  { "index_code": 1, "is_new": 1 },
  { name: "idx_index_isnew" }
)
db.citic_industry_member.createIndex(
  { "cons_code": 1, "is_new": 1 },
  { name: "idx_cons_isnew" }
)
db.citic_industry_member.createIndex(
  { "level": 1, "is_new": 1 },
  { name: "idx_level_isnew" }
)
```

### 3.3 新建集合：`citic_daily`

用途：中信行业指数日行情 + 排名。

文档示例：

```javascript
{
  "ts_code": "CI005001.WI",
  "trade_date": "20260206",
  "name": "银行",
  "level": 1,
  "open": 1023.11,
  "high": 1032.22,
  "low": 1012.33,
  "close": 1020.55,
  "change": -2.10,
  "pct_change": -0.21,
  "vol": 54321.0,
  "amount": 345678.9,
  "rank": 18,
  "rank_total": 30,
  "updated_at": ISODate("2026-02-06T10:00:00Z"),
  "created_at": ISODate("2026-02-06T10:00:00Z")
}
```

索引建议：

```javascript
db.citic_daily.createIndex(
  { "ts_code": 1, "trade_date": 1 },
  { unique: true, name: "idx_ts_code_trade_date" }
)
db.citic_daily.createIndex(
  { "trade_date": 1, "level": 1 },
  { name: "idx_trade_date_level" }
)
db.citic_daily.createIndex(
  { "level": 1, "trade_date": -1, "rank": 1 },
  { name: "idx_level_trade_date_rank" }
)
```

### 3.4 新建集合：`market_index_dailybasic`

用途：大盘指数每日估值指标（来自 `index_dailybasic`）。

文档示例：

```javascript
{
  "ts_code": "000300.SH",
  "trade_date": "20260206",
  "total_mv": 58231.22,
  "float_mv": 51223.10,
  "total_share": 1250.88,
  "float_share": 1090.35,
  "free_share": 982.11,
  "turnover_rate": 0.87,
  "turnover_rate_f": 1.02,
  "total_pe": 15.44,
  "pe": 14.71,
  "pb": 1.52,
  "updated_at": ISODate("2026-02-06T10:00:00Z"),
  "created_at": ISODate("2026-02-06T10:00:00Z")
}
```

索引建议：

```javascript
db.market_index_dailybasic.createIndex(
  { "ts_code": 1, "trade_date": 1 },
  { unique: true, name: "idx_ts_code_trade_date" }
)
db.market_index_dailybasic.createIndex(
  { "trade_date": -1 },
  { name: "idx_trade_date_desc" }
)
```

### 3.5 新建集合：`index_factor_pro`

用途：统一存储指数技术面因子（大盘指数 + 申万行业指数 + 中信行业指数，来自 `idx_factor_pro`）。

文档示例：

```javascript
{
  "ts_code": "000300.SH",
  "trade_date": "20260206",
  "source": "market",      // market | sw | ci
  "ts_name": "沪深300",
  "market": "CSI",
  "macd_dif": 12.31,
  "macd_dea": 10.22,
  "macd": 4.18,
  "rsi_6": 58.66,
  "rsi_12": 55.12,
  "rsi_24": 50.09,
  "pct_change": 0.83,
  "simple_return": 0.0083,
  "log_return": 0.00826,
  "...": "... all other idx_factor_pro fields ...",
  "updated_at": ISODate("2026-02-06T10:00:00Z"),
  "created_at": ISODate("2026-02-06T10:00:00Z")
}
```

索引建议：

```javascript
db.index_factor_pro.createIndex(
  { "ts_code": 1, "trade_date": 1 },
  { unique: true, name: "idx_ts_code_trade_date" }
)
db.index_factor_pro.createIndex(
  { "source": 1, "trade_date": -1 },
  { name: "idx_source_trade_date_desc" }
)
db.index_factor_pro.createIndex(
  { "trade_date": -1 },
  { name: "idx_trade_date_desc" }
)
```

---

## 4. 同步脚本设计

### 4.1 脚本位置与命名

建议新增：

- `backend/scripts/daily/sync_zhishu_data.py`

该脚本统一处理上面 5 个集合（中信维度、中信行情、大盘指标、统一技术因子）。

### 4.2 命令行参数

```bash
# 指定日期区间拉取
python backend/scripts/daily/sync_zhishu_data.py --start-date 20260101 --end-date 20260131

# 冷启动全量拉取（历史）
python backend/scripts/daily/sync_zhishu_data.py --full-history --history-start-date 20050101

# 仅同步中信相关
python backend/scripts/daily/sync_zhishu_data.py --start-date 20260201 --end-date 20260206 --modules citic

# 仅同步大盘指数（可指定指数）
python backend/scripts/daily/sync_zhishu_data.py --start-date 20260201 --end-date 20260206 --modules market --index-codes 000300.SH,000905.SH,399006.SZ
```

参数定义（建议）：

| 参数 | 类型 | 说明 |
|---|---|---|
| `--start-date` | str | 开始日期（YYYYMMDD） |
| `--end-date` | str | 结束日期（YYYYMMDD） |
| `--full-history` | flag | 冷启动模式，按历史全量拉取 |
| `--history-start-date` | str | 全量模式起始日期，默认 `20050101` |
| `--modules` | str | `all`/`citic`/`market` |
| `--index-codes` | str | 大盘指数代码列表，逗号分隔，默认：`000001.SH,399001.SZ,399006.SZ,000300.SH,000905.SH,000852.SH,000688.SH` |
| `--sleep` | float | API 调用间隔秒数 |

### 4.3 数据处理流程（建议）

1. 中信维表同步（`ci_index_member`）  
步骤：按 `L1/L2/L3` + `is_new=Y` 拉取 -> 落 `citic_industry_member` -> 聚合去重更新 `citic_industry`。

2. 中信日行情同步（`ci_daily`）  
步骤：拉取行情 -> 用 `citic_industry` 映射 `name/level` -> 分层计算 `rank/rank_total` -> upsert 到 `citic_daily`。

3. 大盘指标同步（`index_dailybasic`）  
步骤：按 `index_codes + 日期范围` 拉取 -> 标准化数值 -> upsert 到 `market_index_dailybasic`。

4. 技术因子同步（`idx_factor_pro`）  
步骤：按三类指数代码集合（market/sw/ci）+ 日期范围拉取 -> 保留原字段 -> upsert 到 `index_factor_pro`（统一存储，使用 `source` 标识来源）。

5. 非交易日处理  
步骤：复用 `mongo_trade_calendar.is_trading_day` 跳过非交易日。

---

## 5. 前端需求设计

### 5.1 板块排名页改造

当前 `frontend/pages/sector-ranking.js` 现状是单一“板块排名”。设计调整：

1. 文案改为“申万板块排名”。
2. 在同页新增“中信板块排名”入口，推荐使用 `source` 维度切换：
   - `source=sw`（申万，默认）
   - `source=ci`（中信）
3. API 层建议统一为现有接口加 `source` 参数，避免页面重复开发。
4. 中信板块名称支持详情跳转，建议新增中信详情页路由：`/citic-sectors/[index_code]`。

推荐接口形态（兼容原接口）：

- `GET /api/sector-ranking/history?source=sw|ci&level=1...`
- `GET /api/sector-ranking/avg?source=sw|ci&level=1...`
- `GET /api/sector-ranking/dates?source=sw|ci`

### 5.2 “大盘指数”页面设计

建议新增页面：

- 路由：`/market-index`
- 页面名称：`大盘指数`

页面模块：

1. 顶部筛选区  
`指数选择`、`日期区间`、`指标组（估值/技术面）`。

2. 概览卡片（最新交易日）  
展示 `pct_change`、`pe`、`pb`、`turnover_rate`、`total_mv`。

3. 主图（ECharts）  
默认展示 `close`（若后续补 index_daily 可切换 K 线），并可叠加 `MACD/RSI/KDJ`。

4. 因子表格  
分组展示常用因子（趋势、摆动、量能、波动），支持按日期排序。

5. 多指数对比（可选）  
同一因子跨指数对比，例如 `RSI_14` 或 `pct_change`。

配套 API（建议）：

- `GET /api/market-index/overview?trade_date=YYYYMMDD`
- `GET /api/market-index/series?ts_code=000300.SH&start_date=...&end_date=...`
- `GET /api/market-index/factors?ts_code=000300.SH&start_date=...&end_date=...`
- `GET /api/market-index/dates?limit=30`

---

## 6. 已确认项

1. 大盘指数代码范围采用默认集合：`000001.SH, 399001.SZ, 399006.SZ, 000300.SH, 000905.SH, 000852.SH, 000688.SH`。
2. 中信成分同步策略：`is_new=Y`，不拉 `is_new=N` 历史成分。
3. 中信板块排名中的板块名称需要支持详情跳转。
4. 脚本参数统一使用短横线风格：`--start-date`、`--end-date`。

## 7. 待你确认（新增问题）

关于 `idx_factor_pro` 同时覆盖大盘/申万/中信三类指数，推荐方案是：

1. 统一存到单独集合 `index_factor_pro`（而不是拆 3 张因子表）。
2. 用 `source` 字段区分 `market`/`sw`/`ci`。
3. 各业务表（`shenwan_daily`、`citic_daily`、`market_index_dailybasic`）不冗余因子字段，查询时按 `(ts_code, trade_date)` 关联。

该方案优点是字段维护成本最低、扩展性最好。若你同意，我后续就按这个方案开发。

---

## 8. 参考文档

- `https://tushare.pro/document/2?doc_id=373`（中信行业成分）
- `https://tushare.pro/document/2?doc_id=308`（中信行业日线）
- `https://tushare.pro/document/2?doc_id=128`（指数每日指标）
- `https://tushare.pro/document/2?doc_id=358`（指数技术面因子）
