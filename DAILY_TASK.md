# Daily Tasks

## 0) Use `backend/scripts/daily/daily.sh` (推荐)

一键执行日常任务（拉取日线 -> 同步技术因子 -> 计算信号 -> 同步申万日线）。

```bash
# 在项目根目录执行（默认跑当天）
bash backend/scripts/daily/daily.sh

# 指定开始日期（结束日期默认今天）
bash backend/scripts/daily/daily.sh --start-date 20260201

# 指定日期区间
bash backend/scripts/daily/daily.sh --start-date 20260201 --end-date 20260206
```

参数说明：

- `--start-date`：开始日期，支持 `YYYYMMDD` 或 `YYYY-MM-DD`
- `--end-date`：结束日期，支持 `YYYYMMDD` 或 `YYYY-MM-DD`，不传默认今天

日志输出：

- `logs/daily_*.log`

---

## 1) Pull daily market data (K-line)

```bash
python backend/scripts/daily/pull_daily_history.py --last-days 1
python backend/scripts/daily/pull_daily_history.py --start-date 20260202
python backend/scripts/daily/pull_daily_history.py --start-date 20240101 --end-date 20240131
```

## 2) Sync stock factors

```bash
python backend/scripts/daily/sync_stk_factor_pro.py --last-days 1
python backend/scripts/daily/sync_stk_factor_pro.py --trade-date 20260206
python backend/scripts/daily/sync_stk_factor_pro.py --start-date 20260101 --end-date 20260206
```

## 3) Calculate daily signals

计算指定日期的交易信号（BUY信号）并存储到MongoDB。

```bash
cd /home/james/projects/freedom/backend && python -m scripts.daily.calculate_signal --start-date 20260126
# 计算今天的信号（日期格式：YYYYMMDD 或 YYYY-MM-DD）
python backend/scripts/daily/calculate_signal.py --given-date 20260202
```

Optional ranges:

```bash
# 计算日期区间内的所有交易日信号
python backend/scripts/daily/calculate_signal.py --start-date 20260126 --end-date 20260126
# 或
python backend/scripts/daily/calculate_signal.py --start-date 2024-01-01 --end-date 2024-01-31
```

**注意**：
- 脚本会自动检查是否为交易日，非交易日会跳过
- 使用的策略：`EarlyBreakoutSignalModel` 和 `DailySignalModel`
- 结果存储在 MongoDB 的 `daily_signal` collection 中

## 4) Sync Shenwan industry members

同步申万行业成分股（当前最新成分 + 标记已剔除）。板块有新增或删除股票时，建议每日执行一次。

```bash
python backend/scripts/daily/sync_shenwan_members.py --incremental
```

**说明**：
- 不加 `--incremental`：只拉取并 upsert 当前最新成分股，新增会同步，已剔除的股票不会自动标记
- 加 `--incremental`：在拉取最新成分后，对比库内 `is_new=Y` 的记录，将本次不在列表中的标记为 `is_new=N`、`out_date=当天`，新增和剔除都会与 TuShare 一致
- 结果存储在 MongoDB 的 `shenwan_industry_member` collection 中

## 5) Sync Shenwan daily index (板块日行情与排名)

同步申万行业日线行情（TuShare sw_daily），按日计算各层级涨跌幅排名并写入 MongoDB，供板块排名页使用。

```bash
# 同步最近 1 天（常用，盘后执行）
python backend/scripts/daily/sync_shenwan_daily.py --last-days 1

# 同步指定单日
python backend/scripts/daily/sync_shenwan_daily.py --trade-date 20260202

# 同步最近 N 天
python backend/scripts/daily/sync_shenwan_daily.py --last-days 5

# 同步日期区间（全量补历史时用）
python backend/scripts/daily/sync_shenwan_daily.py --start-date 20240101 --end-date 20241231
```

**说明**：
- 脚本会先查 `trade_calendar`，若该日 `is_open=0` 则跳过，不调用 API
- 通过 `ts_code` 关联 `shenwan_industry.index_code` 获取 `level`，对 level=1/2/3 按涨跌幅计算当日排名（`rank`、`rank_total`）
- 综合指数（如申万50）无 level，不参与排名，仅存储行情
- 结果存储在 MongoDB 的 `shenwan_daily` collection 中
- 可选 `--sleep`（默认 0）控制每次 API 调用间隔，单位秒

## 6) Compact Parquet partitions

用于合并 `data/raw/` 下分区中的多个 `part-*.parquet`，去重并压缩为单个文件，减少碎片，提高后续 DuckDB 查询效率。

### 6.1 Compact daily Parquet（K线日线）

```bash
# 全量压缩所有 ts_code/year 分区
python backend/scripts/daily/compact_daily_parquet.py

# 只压缩某个股票某一年
python backend/scripts/daily/compact_daily_parquet.py --ts-code 000001.SZ --year 2024
```

**说明**：
- 作用目录：`data/raw/daily/ts_code=*/year=*/`
- 去重逻辑：按 `(ts_code, trade_date)` 去重

### 6.2 Compact daily_basic Parquet（每日指标）

```bash
# 全量压缩所有 ts_code/year 分区
python backend/scripts/daily/compact_daily_basic_parquet.py

# 只压缩某个股票某一年
python backend/scripts/daily/compact_daily_basic_parquet.py --ts-code 000001.SZ --year 2024
```

**说明**：
- 作用目录：`data/raw/daily_basic/ts_code=*/year=*/`
- 去重逻辑：`SELECT DISTINCT *`
