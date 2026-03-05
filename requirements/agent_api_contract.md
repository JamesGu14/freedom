# Freedom Agent 对接接口字典（已实现）

> 生成日期：2026-03-04
> 适配基线：`backend/app/api/routes/agent_required_api.py`
> Base URL：`/api`
> 认证：`Authorization: Bearer <token>`
> 文档入口：`/api/docs`，Schema：`/api/openapi.json`

## 1. 通用约定

- 股票代码：`ts_code`，如 `000001.SZ`
- 代码兼容：支持无后缀输入（如 `600118`），服务端会自动解析为标准 `ts_code`
- 日期：支持 `YYYYMMDD` 与 `YYYY-MM-DD` 输入，返回一般为 `YYYYMMDD`
- 通用响应结构：

```json
{
  "code": 200,
  "data": [],
  "total": 0,
  "page": 1,
  "page_size": 200
}
```

说明：
- 非分页接口通常只返回 `code + data`
- 分页接口会额外返回 `total/page/page_size`
- 若对应数据源暂无数据，返回 `code=200` 且 `data=[]`（不抛 500）

---

## 2. 已实现接口清单（42个）

### 2.1 股票基础与行情

1. `GET /stocks/basic`
- 参数：`market` `exchange` `ts_codes` `page` `page_size`
- 返回关键字段：`ts_code symbol name industry market exchange list_date`

2. `GET /stocks/basic/{ts_code}`
- 返回关键字段：同上（单条）

3. `GET /stocks/search`
- 参数：`q` `limit`
- 说明：匹配 `ts_code/symbol/name`

4. `GET /stocks/{ts_code}/daily`
- 参数：`start_date` `end_date` `adj(qfq/hfq/none)` `fields`
- 返回关键字段：`trade_date open high low close pre_close change pct_chg vol amount`

5. `POST /stocks/daily/batch`
- Body：`ts_codes[] trade_date adj`
- 返回：多股票当日横截面行情

6. `GET /stocks/{ts_code}/daily/recent`
- 参数：`n` `adj` `fields`
- 返回：最近 N 个交易日行情

7. `GET /stocks/daily/snapshot`
- 参数：`trade_date(默认最新)` `ts_codes` `fields` `page` `page_size`
- 返回：全市场（或指定股票）当日行情快照

8. `GET /stocks/{ts_code}/daily-basic`
- 参数：`start_date` `end_date` `fields`
- 返回关键字段：`turnover_rate pe_ttm pb dv_ratio total_mv circ_mv ...`

9. `GET /stocks/daily-basic/snapshot`
- 参数：`trade_date` + 条件筛选（`pe_ttm_max pb_max total_mv_min total_mv_max dv_ratio_min turnover_rate_max`）+ 分页

10. `GET /stocks/{ts_code}/indicators`
- 参数：`start_date` `end_date` `fields`
- 返回：指标全字段或按 `fields` 裁剪（如 `ma20,macd,rsi12`）

11. `GET /stocks/{ts_code}/limit-prices`
- 参数：`start_date` `end_date`
- 返回关键字段：`trade_date pre_close up_limit down_limit`

12. `GET /stocks/limit-prices/snapshot`
- 参数：`trade_date(默认最新)` `ts_codes` `page` `page_size`

### 2.2 行业（申万 / 中信）

13. `GET /industry/shenwan/tree`
- 参数：`level` `version`
- 说明：`level` 不传时返回树形结构（含 `children`）

14. `GET /industry/shenwan/members`
- 参数：`industry_code` `level` `is_new` `ts_code` `version` `page` `page_size`

15. `GET /industry/shenwan/daily`
- 参数：`trade_date` 或 `start_date+end_date` `level` `industry_code` `order_by(rank/pct_change)` 分页

16. `GET /industry/shenwan/daily/ranking`
- 参数：`trade_date` `period(1d/5d/10d/20d/60d)`
- 返回：行业期间涨跌幅排行

17. `GET /industry/citic/tree`
- 参数：`level`

18. `GET /industry/citic/members`
- 参数：`industry_code` `level` `is_new` `ts_code` `page` `page_size`

19. `GET /industry/citic/daily`
- 参数：`trade_date` 或 `start_date+end_date` `level` `industry_code` 分页

### 2.3 指数与交易日历

20. `GET /market-index/daily-basic`
- 参数：`ts_codes` `trade_date` 或 `start_date+end_date` 分页
- 返回关键字段：`ts_code trade_date total_mv float_mv pe pb turnover_rate ...`

21. `GET /market-index/factors`
- 参数：`ts_code` `source(market/sw/ci)` `start_date` `end_date` `limit`
- 返回：`index_factor_pro` 对应技术因子字段

22. `GET /trade-calendar`
- 参数：`exchange` `start_date` `end_date` `is_open`
- 返回关键字段：`cal_date is_open pretrade_date exchange`

23. `GET /trade-calendar/latest-trade-date`
- 参数：`exchange`
- 返回：`{"trade_date": "YYYYMMDD"}`

### 2.4 财务与分红

24. `GET /stocks/{ts_code}/financials/indicators`
- 参数：`period` `period_type(annual/quarterly)` `limit`
- 数据集合：`financial_indicators`

25. `GET /stocks/{ts_code}/financials/income`
- 参数：`period` `limit`
- 数据集合：`income_statement`

26. `GET /stocks/{ts_code}/financials/balance`
- 参数：`period` `limit`
- 数据集合：`balance_sheet`

27. `GET /stocks/{ts_code}/financials/cashflow`
- 参数：`period` `limit`
- 数据集合：`cashflow`

28. `POST /stocks/financials/indicators/batch`
- Body：`ts_codes[] period fields[]`
- 返回：每只股票最新一期财务指标快照

29. `GET /stocks/financials/indicators/screen`
- 参数：`period roe_min revenue_yoy_min n_income_yoy_min debt_to_assets_max netprofit_margin_min fcf_positive page page_size`

30. `GET /stocks/{ts_code}/dividends`
- 参数：`limit`
- 数据集合：`dividend_history`

31. `GET /stocks/{ts_code}/dividends/summary`
- 返回关键字段：`consecutive_years avg_dv_ratio_5y total_cash_div_5y latest_dv_ratio payout_ratio`

32. `GET /stocks/dividends/screen`
- 参数：`dv_ratio_min consecutive_years_min payout_ratio_max total_mv_min page page_size`

### 2.5 董监高 / 宏观 / 事件

33. `GET /stocks/{ts_code}/insider-trades`
- 参数：`start_date end_date holder_type trade_type page page_size`
- 数据集合：`insider_trades`

34. `GET /market/insider-trades/latest`
- 参数：`trade_type days min_amount page page_size`

35. `GET /macro/money-supply`
36. `GET /macro/lpr`
37. `GET /macro/pmi`
38. `GET /macro/cpi-ppi`
39. `GET /macro/social-financing`
- 公共参数：`start_date end_date limit`
- 数据集合：`macro_indicators`（按 `indicator` 字段区分）

40. `GET /stocks/{ts_code}/events/buyback`
41. `GET /market/events/ma-restructure`
42. `GET /stocks/{ts_code}/events/holder-changes`
- 数据集合：`corporate_events`（按 `event_type` 区分）

> 说明：共 42 个可用接口，其中 41 个在 `agent_required_api.py`，`/market-index/factors` 复用并增强了既有路由。

---

## 3. 对接建议（给 Agent）

- 优先用这些高频接口做主流程：
  - `/stocks/basic`
  - `/stocks/daily/snapshot`
  - `/stocks/daily-basic/snapshot`
  - `/industry/shenwan/members`
  - `/industry/shenwan/daily/ranking`
  - `/trade-calendar/latest-trade-date`
- 对 B 类数据（财务/分红/宏观/事件），先做“空数据可降级”逻辑：
  - `data == []` 时回退到可用维度，不要视为接口错误

---

## 4. 文件与代码定位

- 接口实现：`backend/app/api/routes/agent_required_api.py`
- 路由注册：`backend/app/api/routers.py`
- 模块导出：`backend/app/api/routes/__init__.py`
- 指数因子 source 扩展：
  - `backend/app/api/routes/market_index.py`
  - `backend/app/data/mongo_market_index.py`

---

## 5. 自选分组 CRUD（新增）

> 说明：自选分组沿用现有 `stock-groups` 模型（全局共享，允许重名）。

1. `GET /stock-groups`
- 返回：分组列表（含 `id name created_at count`）

2. `POST /stock-groups`
- Body: `{ \"name\": \"大盘核心\" }`
- 返回：新建分组对象

3. `GET /stock-groups/{group_id}`
- 返回：单个分组详情（含 `count`）

4. `PUT /stock-groups/{group_id}`  ✅ 新增
- Body: `{ \"name\": \"新分组名\" }`
- 返回：更新后的分组对象

5. `DELETE /stock-groups/{group_id}`  ✅ 新增
- 行为：级联硬删除分组及其全部分组项
- 返回：`{ \"deleted\": true, \"group_id\": \"...\", \"deleted_items\": 3 }`

6. `GET /stock-groups/{group_id}/stocks`
- 返回：分组内股票列表（含最新涨跌字段）

7. `POST /stock-groups/{group_id}/stocks`
- Body: `{ \"ts_code\": \"000001.SZ\" }`
- 返回：`{ \"added\": true/false }`

8. `DELETE /stock-groups/{group_id}/stocks/{ts_code}`
- 返回：`{ \"removed\": true/false }`
