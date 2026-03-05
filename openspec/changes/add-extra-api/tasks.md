# Tasks: 新增9个 TuShare 数据接口

## Phase 1: TuShare Client & 基础设施

- [ ] **T1** 在 `backend/app/data/tushare_client.py` 新增8个 fetch 函数
  - `fetch_cyq_perf(ts_code, start_date, end_date, trade_date)`
  - `fetch_cyq_chips(ts_code, trade_date)`
  - `fetch_ccass_hold(ts_code, start_date, end_date, trade_date)`
  - `fetch_hk_hold(ts_code, start_date, end_date, trade_date, exchange)`
  - `fetch_stk_surv(ts_code, start_date, end_date, trade_date)`
  - `fetch_moneyflow_dc(ts_code, start_date, end_date, trade_date)`
  - `fetch_moneyflow_hsgt(start_date, end_date, trade_date)`
  - `fetch_idx_factor_pro(ts_code, start_date, end_date, trade_date)`
  - 每个函数使用已有的 `_request_with_retry` + `_query_pro`（4次重试，指数退避），遵循已有风格
  - 所有函数优先支持按日期批量拉取，减少总调用次数

- [ ] **T2** 新增 MongoDB 数据层模块
    - `backend/app/data/mongo_ccass_hold.py` — upsert / query
  - `backend/app/data/mongo_hk_hold.py` — upsert / query
  - `backend/app/data/mongo_stk_surv.py` — upsert / query
  - `backend/app/data/mongo_moneyflow_hsgt.py` — upsert / query
  - 每个模块包含：创建索引函数、upsert_batch、query_by_ts_code、query_by_date_range

## Phase 2: 同步脚本（每日增量 + 全量历史）

- [ ] **T3** `backend/scripts/daily/sync_cyq_perf.py`
  - 按交易日拉取全市场筹码胜率
  - 存为 Parquet：`data/features/cyq_perf/ts_code={ts_code}/year={year}/`
  - 支持 `--start-date/--end-date/--last-days/--trade-date`
  - 跳过非交易日，调用 `mark_sync_done`

- [ ] **T4** `backend/scripts/daily/sync_moneyflow_dc.py`（原T5，重新编号） `backend/scripts/daily/sync_moneyflow_dc.py`
  - 按交易日拉取东方财富资金流向（历史数据起点 2023-09-11）
  - 存为 Parquet：`data/features/moneyflow_dc/ts_code={ts_code}/year={year}/`

- [ ] **T6** `backend/scripts/daily/sync_idx_factor_pro.py`
  - 读取 MongoDB 中已知指数列表（从 `market_index` 集合或预定义列表）
  - 按指数逐只拉取，单次最多8000条
  - 存为 Parquet：`data/features/idx_factor_pro/ts_code={ts_code}/year={year}/`

- [ ] **T7** `backend/scripts/daily/sync_moneyflow_hsgt.py`
  - 拉取沪深港通整体资金流向
  - upsert 到 MongoDB `moneyflow_hsgt` 集合

- [ ] **T8** `backend/scripts/daily/sync_ccass_hold.py`
  - 按日期拉取 CCASS 持股汇总
  - upsert 到 MongoDB `ccass_hold` 集合

- [ ] **T9** `backend/scripts/daily/sync_hk_hold.py`
  - 分 SH / SZ / HK 三个 exchange 拉取
  - upsert 到 MongoDB `hk_hold` 集合

- [ ] **T10** `backend/scripts/daily/sync_cyq_chips.py`
  - 历史全量：按 ts_code 循环，每只股票拉取全部历史日期段（减少总调用次数）
  - 每日增量：对当日有交易的股票，按 trade_date 拉取（或仍按 ts_code 拉最近N天）
  - 存为 Parquet：`data/features/cyq_chips/ts_code={ts_code}/year={year}/`

- [ ] **T11** `backend/scripts/daily/sync_stk_surv.py`
  - 按日期段分页拉取（每次100条）
  - upsert 到 MongoDB `stk_surv` 集合
  - **每周五**自动运行（与 shenwan 成员同步同步骤），拉取最近7天新增调研记录

## Phase 3: API 路由

- [ ] **T12** 新建 `backend/app/api/routes/market_data.py`
  - `GET /api/chip-perf/{ts_code}` — 查询 Parquet cyq_perf
  - `GET /api/chip-distribution/{ts_code}` — 查询 Parquet cyq_chips，支持按 trade_date 过滤
  - `GET /api/ccass-hold/{ts_code}` — 查询 MongoDB ccass_hold
  - `GET /api/hk-hold/{ts_code}` — 查询 MongoDB hk_hold，支持 exchange 过滤
  - `GET /api/institution-survey/{ts_code}` — 查询 MongoDB stk_surv
  - `GET /api/moneyflow-hsgt` — 查询 MongoDB moneyflow_hsgt（无 ts_code 参数）
  - `GET /api/index-factors/{ts_code}` — 查询 Parquet idx_factor_pro
  - 所有 `{ts_code}` 路径参数通过 `resolve_ts_code_input()` 兼容 `600118` 格式
  - 公共 Query 参数：`start_date`, `end_date`；可选 `limit`（默认250）

- [ ] **T13** 新建 `backend/app/services/market_data_service.py`
  - 封装 DuckDB 查询（Parquet 数据）和 MongoDB 查询的业务逻辑
  - 统一返回 Python list[dict]，排序：trade_date 降序
  - Parquet 查询复用已有 `duckdb_client` 或直接 `duckdb.connect()`

- [ ] **T14** 注册路由
  - 在 `backend/app/api/routes/__init__.py` 导入 `market_data_router`
  - 在 `backend/app/api/routers.py` 挂载路由

## Phase 4: daily.sh 集成

- [ ] **T15** 更新 `backend/scripts/daily/daily.sh`
  - `TOTAL_STEPS` 从7改为12（stk_surv 不计入自动步骤）
  - 新增步骤8-12（cyq_perf, cyq_chips, moneyflow, hsgt, ccass/hk, idx_factor）
  - ccass_hold + hk_hold 仅周五运行（与成员同步保持一致）
  - cyq_chips 每日运行，写入后自动清理60日以外数据

## Phase 5: OpenAPI 更新

- [ ] **T16** 验证 openapi.json 自动更新
  - FastAPI 在 `GET /api/openapi.json` 自动生成 schema，新路由注册后无需额外操作
  - 验证步骤：启动服务后访问 `/api/docs`，确认所有新端点出现在 Swagger UI 中

## 全量历史同步命令参考

```bash
# 筹码胜率（2018起）
python backend/scripts/daily/sync_cyq_perf.py --start-date 20180101 --end-date 20261231 --sleep 2

# 东方财富资金流（2023-09-11起）
python backend/scripts/daily/sync_moneyflow_dc.py --start-date 20230911 --end-date 20261231 --sleep 1.5

# 指数技术因子（全量）
python backend/scripts/daily/sync_idx_factor_pro.py --start-date 20150101 --end-date 20261231 --sleep 2

# 港通资金流（2015起）
python backend/scripts/daily/sync_moneyflow_hsgt.py --start-date 20150101 --end-date 20261231

# CCASS（全量）
python backend/scripts/daily/sync_ccass_hold.py --start-date 20150101 --end-date 20261231 --sleep 2

# 港股通持股（2015起）
python backend/scripts/daily/sync_hk_hold.py --start-date 20150101 --end-date 20261231 --sleep 2

# 机构调研（按需）
python backend/scripts/daily/sync_stk_surv.py --start-date 20150101 --end-date 20261231 --sleep 1.5
```

## 依赖关系

```
T1 (tushare_client)
  ↓
T2 (mongo层) ← T3~T11 (同步脚本) ← T15 (daily.sh)
  ↓               ↓
T13 (service层)
  ↓
T12 (路由) → T14 (注册) → T16 (openapi)
```
