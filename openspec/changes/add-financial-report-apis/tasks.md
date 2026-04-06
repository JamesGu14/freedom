## 1. TuShare Client - 新增 5 个 fetch 函数

- [ ] 1.1 在 `tushare_client.py` 新增 `fetch_forecast(ts_code, ann_date, start_date, end_date, period, type, limit, offset)` — ts_code 可选，支持按 ann_date 范围查全市场
- [ ] 1.2 在 `tushare_client.py` 新增 `fetch_express(ts_code, ann_date, start_date, end_date, period, limit, offset)` — ts_code 可选，支持按 ann_date 范围查全市场
- [ ] 1.3 在 `tushare_client.py` 新增 `fetch_fina_audit(ts_code, ann_date, start_date, end_date, period, limit, offset)` — **ts_code 必填**
- [ ] 1.4 在 `tushare_client.py` 新增 `fetch_fina_mainbz(ts_code, period, type, start_date, end_date, limit, offset)` — **ts_code 必填**，start_date/end_date 含义是**报告期范围**（非公告日期）
- [ ] 1.5 在 `tushare_client.py` 新增 `fetch_disclosure_date(ts_code, end_date, pre_date, actual_date, limit, offset)` — end_date 是**报告期**（如 20241231），max 3000 条/次

## 2. DuckDB 存储层 - 新增 5 张表和 upsert 函数

- [ ] 2.1 定义 `_FORECAST_COLUMNS` 并创建 `forecast` 表（含 ts_code, ann_date, end_date, type, p_change_min, p_change_max, net_profit_min, net_profit_max, last_parent_net, first_ann_date, summary, change_reason, raw_payload）
- [ ] 2.2 定义 `_EXPRESS_COLUMNS` 并创建 `express` 表（含 ts_code, ann_date, end_date, revenue, operate_profit, total_profit, n_income, total_assets, total_hldr_eqy_exc_min_int, diluted_eps, diluted_roe, yoy_net_profit, bps, perf_summary, is_audit, raw_payload）
- [ ] 2.3 定义 `_FINA_AUDIT_COLUMNS` 并创建 `fina_audit` 表（含 ts_code, ann_date, end_date, audit_result, audit_fees, audit_agency, audit_sign, raw_payload）
- [ ] 2.4 定义 `_FINA_MAINBZ_COLUMNS` 并创建 `fina_mainbz` 表（含 ts_code, end_date, bz_item, bz_sales, bz_profit, bz_cost, curr_type, update_flag, raw_payload）。实现时通过实际 API 调用确认是否有 bz_code 等额外字段
- [ ] 2.5 定义 `_DISCLOSURE_DATE_COLUMNS` 并创建 `disclosure_date` 表（含 ts_code, end_date, ann_date, pre_date, actual_date, modify_date, raw_payload）
- [ ] 2.6 实现 `upsert_forecast(df)` — 主键 `(ts_code, ann_date, end_date)`
- [ ] 2.7 实现 `upsert_express(df)` — 主键 `(ts_code, ann_date, end_date)`
- [ ] 2.8 实现 `upsert_fina_audit(df)` — 主键 `(ts_code, ann_date, end_date)`
- [ ] 2.9 实现 `upsert_fina_mainbz(df)` — 主键 `(ts_code, end_date, bz_item, curr_type)`
- [ ] 2.10 实现 `upsert_disclosure_date(df)` — 主键 `(ts_code, end_date)`

## 3. 同步脚本 - 扩展 sync_financial_reports.py（仅 forecast / express）

- [ ] 3.1 扩展 `parse_args()` 的 `--dataset` choices，新增 forecast / express（不含 fina_audit）
- [ ] 3.2 扩展 `fetch_dataset_page()` 函数，新增 forecast / express 两个分支（按 ann_date 窗口分页，与 income 等完全一致）
- [ ] 3.3 扩展 `_upsert_dataset()` 函数，新增 forecast / express 的 upsert 分支
- [ ] 3.4 新增 import 语句，引入 `fetch_forecast, fetch_express, upsert_forecast, upsert_express`

## 4. 同步脚本 - 新建 sync_fina_audit.py

- [ ] 4.1 新建 `backend/scripts/daily/sync_fina_audit.py`，支持 CLI 参数：`--start-date`/`--end-date`（公告日期范围）、`--last-days`（默认 30）、`--ts-codes`（逗号分隔，测试用）、`--sleep`（默认 1.0）
- [ ] 4.2 实现主循环：从 MongoDB stock_basic 获取全部 ts_code → 逐只调用 `fetch_fina_audit(ts_code=code, start_date=start, end_date=end)` → upsert 到 DuckDB
- [ ] 4.3 空数据优雅处理：空 DataFrame 记录 debug 日志并 continue
- [ ] 4.4 `mark_sync_done(end_date, 'sync_fina_audit')` 仅在全部股票遍历完成后调用
- [ ] 4.5 使用 tqdm 进度条，set_postfix 显示当前 ts_code / 已处理数 / upserted 数

## 5. 同步脚本 - 新建 sync_fina_mainbz.py

- [ ] 5.1 新建 `backend/scripts/daily/sync_fina_mainbz.py`，支持 CLI 参数：`--period`（单个报告期如 20241231）、`--period-start`/`--period-end`（报告期范围，注意：不是公告日期）、`--ts-codes`（逗号分隔，测试用）、`--sleep`（默认 1.5）
- [ ] 5.2 实现主循环：从 MongoDB stock_basic 获取全部 ts_code → 逐只调用 `fetch_fina_mainbz(ts_code=code, period=period)` 或 `fetch_fina_mainbz(ts_code=code, start_date=period_start, end_date=period_end)` → upsert 到 DuckDB
- [ ] 5.3 分页处理：if `len(df) == 100` 则 offset += 100 继续翻页
- [ ] 5.4 空数据/退市股票优雅处理：空 DataFrame 记录 debug 日志并 continue
- [ ] 5.5 mark_sync_done 策略：`--period` 模式在全部股票遍历完成后调用 `mark_sync_done(period, 'sync_fina_mainbz')`；`--period-start/--period-end` 模式遍历范围内每个报告期各自独立标记；中途失败不标记当前 period
- [ ] 5.6 使用 tqdm 进度条

## 6. 同步脚本 - 新建 sync_disclosure_date.py

- [ ] 6.1 新建 `backend/scripts/daily/sync_disclosure_date.py`，支持 CLI 参数：`--year`（如 2024，遍历 0331/0630/0930/1231）、`--period`（单个报告期如 20241231）、`--recent N`（最近 N 个报告期，基于当前日期推算）、`--sleep`（默认 0.5）
- [ ] 6.2 实现 `--recent` 逻辑：根据当前日期计算最近 N 个报告期（如 2025-06-15 → recent 2 = [20250331, 20250630]）
- [ ] 6.3 实现按报告期查询：`fetch_disclosure_date(end_date=period)` + offset 分页（max 3000 条/次，while `len(df) == limit` 继续翻页）
- [ ] 6.4 `mark_sync_done(period, 'sync_disclosure_date')` 按报告期标记
- [ ] 6.5 使用 tqdm 进度条按报告期迭代

## 7. 调度集成

- [ ] 7.1 在 `daily.sh` 中补充 forecast / express / fina_audit / disclosure_date 的本地手工同步入口，并明确 `fina_mainbz` 不走每日脚本
- [ ] 7.2 在 `backend/scripts/daily/docker-daily.sh` 中加入与 `daily.sh` 对齐的同步步骤，避免容器/API 触发链路漏跑新任务
- [ ] 7.3 在 `backend/app/airflow_sync/daily_sync_registry.py` 中注册新同步任务或补充现有财报编排，确保共享 Airflow 日常同步链路会更新新表
- [ ] 7.4 为 `fina_audit` 明确非每日全市场执行策略：避免直接使用 `--last-days 30` 扫全量股票，改为低频全量、分批轮转或仅对增量股票集合执行
- [ ] 7.5 为 `fina_mainbz` 明确季度/半年度执行策略，并在调度文档中注明其与日常增量脚本分离
- [ ] 7.6 为 `forecast` / `express` / `disclosure_date` 保持按公告日期或报告期的日常增量同步，并记录最终命令参数

## 8. 验证

- [ ] 8.1 手动运行 `sync_financial_reports.py --dataset forecast --last-days 30` 验证正常
- [ ] 8.2 手动运行 `sync_financial_reports.py --dataset express --last-days 30` 验证正常
- [ ] 8.3 手动运行 `sync_fina_audit.py --ts-codes 000001.SZ,600000.SH --last-days 365` 验证单只股票正常
- [ ] 8.4 手动运行 `sync_fina_mainbz.py --ts-codes 000001.SZ,600000.SH --period 20241231` 验证正常，确认分页逻辑
- [ ] 8.5 手动运行 `sync_disclosure_date.py --period 20241231` 验证正常，确认 offset 分页生效
- [ ] 8.6 用 DuckDB CLI 验证 5 张新表有数据：`duckdb data/quant.duckdb "SELECT COUNT(*) FROM forecast; SELECT COUNT(*) FROM express; ..."`

## 9. 文档

- [ ] 9.1 更新 `docs/tushare_5000积分接口实现对照.md`，将 5 个接口移入已实现清单
