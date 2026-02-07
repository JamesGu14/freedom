# 量化策略与回测系统设计（基于现有 DB 数据）

## 1. 目标

基于当前项目已有数据（交易日历、个股日线/日指标/技术因子、申万/中信板块、大盘指数、指数因子），构建一个可落地的日频多因子选股与回测框架，支持：

1. 每日全市场扫描并生成买卖信号。
2. 生成具体仓位建议（买入金额/股数、减仓比例、止损止盈）。
3. 回测输出净值、最大回撤、收益、交易明细等核心指标。
4. 前端展示回测曲线、买卖点、回撤曲线与交易记录。

本文是策略与系统设计文档，不包含代码实现。

---

## 2. 数据前提与约束

## 2.1 可用数据（按 DB.md）

1. 个股：
- `raw/daily`：OHLCV、涨跌幅（历史完整）。
- `raw/daily_basic`：估值、换手率、市值等（历史完整）。
- `features/indicators`：MA/MACD/KDJ/RSI/BOLL/ATR/CCI/WR/量比等（历史完整）。

2. 板块与指数：
- `shenwan_daily`、`citic_daily`：板块日行情 + 排名。
- `market_index_dailybasic`：大盘指数估值/市值等。
- `index_factor_pro`：大盘/申万/中信指数技术因子。

3. 交易辅助：
- `trade_calendar`：交易日历（SSE）。
- `daily_signal`：策略信号存储（可复用）。

## 2.2 约束与说明

1. 当前无财报三表（利润表/资产负债表/现金流），因此“基本面”以估值与市场行为代理因子实现。
2. 策略采用日频，默认 `T` 日收盘后生成信号，`T+1` 开盘成交。
3. 默认回测区间：`20100104` 到 `20260206`（以交易日历开市日为准）。

---

## 3. 策略总体架构

采用四层框架：

1. 市场状态层（Market Regime）  
决定总仓位上限（风险开关）。

2. 板块趋势层（Sector Trend）  
优先选择强板块，避免逆板块交易。

3. 个股因子层（Stock Factors）  
对个股做多因子打分，产生候选池与排序。

4. 组合与风控层（Portfolio + Risk）  
执行仓位分配、止损止盈、换仓规则。

---

## 4. 因子设计

## 4.1 市场状态因子（大盘风控）

基于 `000300.SH`、`000001.SH` 及板块广度构建三档风险状态：

1. `RiskOn`（进攻）：
- `close > MA20 > MA60`
- `MACD` 柱为正或 DIF 上穿 DEA
- 近 5 日申万一级板块上涨家数占比 >= 60%

2. `Neutral`（中性）：
- 趋势不一致，或板块广度在 40%-60%

3. `RiskOff`（防守）：
- `close < MA60` 且 `MACD` 弱势
- 近 5 日板块上涨占比 <= 40%

输出：`market_regime_score` in {1.0, 0.6, 0.3}，作为总仓位上限乘数。

## 4.2 板块趋势因子（申万+中信）

按日计算板块强度，并映射到个股：

1. 板块强度 `sector_strength`：
- 20 日动量（`pct_chg_20d`）
- 5 日动量（`pct_chg_5d`）
- 排名因子（`rank`、`rank_avg_5d`，越靠前越强）

2. 归一化后加权：
- `0.5 * rank_score + 0.3 * mom_20d_score + 0.2 * mom_5d_score`

3. 个股映射：
- 优先取申万三级行业；
- 若缺失可回落到中信行业映射；
- 同时保留申万与中信两个分数，取加权平均。

## 4.3 个股“基本面代理”因子

使用 `daily_basic + indicators` 的可得字段：

1. 估值因子（行业内分位）：
- 低 `PE_TTM`、低 `PB` 得高分（分位逆序）。

2. 流动性因子：
- `amount_20d_avg`、`turnover_rate_20d_avg`（剔除极端冷门票）。

3. 稳定性因子：
- `ATR / close` 越低，分数越高（降低噪声票）。

4. 资金活跃因子：
- `volume_ratio`、`turnover_rate` 在合理区间加分（防止无量突破）。

## 4.4 个股趋势/技术因子

1. 趋势结构：
- `MA20 > MA60`，`close > MA20`。

2. 动量确认：
- `MACD` 金叉或柱状图连续抬升。
- `RSI12` 在 `[50, 80]` 区间优先。

3. 位置与突破：
- 近 20 日新高突破 + 成交量放大（`volume_ratio > 1.2`）。

4. 过热抑制：
- `RSI12 > 85` 或单日涨幅过大（如 > 9%）降分/禁买。

---

## 5. 综合评分与选股逻辑

## 5.1 股票池过滤（硬条件）

每日扫描全量 A 股后，先过滤：

1. 上市天数 < 120 交易日剔除。
2. 最近 20 日平均成交额 < 3000 万剔除。
3. 当日停牌、无行情、异常数据剔除。
4. 当日涨停且无法买入的标的剔除（可通过 `daily_limit` + 开收盘位置判断）。

## 5.2 综合打分

`total_score = 0.35*stock_trend + 0.25*sector_strength + 0.25*value_quality + 0.15*liquidity_stability`

输出分数标准化到 `[0, 100]`。

## 5.3 买入信号

满足：

1. `market_regime_score > 0.3`（非极端风控）。
2. `total_score >= buy_threshold`（建议默认 75）。
3. 在当日排名前 `N`（建议 20）且不在持仓中。

生成 `BUY`，并给出目标仓位（见第 7 节）。

## 5.4 卖出信号

任一触发即 `SELL`：

1. 趋势破坏：`close < MA20` 且 `MACD` 转弱。
2. 止损：从买入价回撤超过 `stop_loss_pct`（默认 8%）。
3. 跟踪止盈：从最高价回撤超过 `trail_stop_pct`（默认 10%）。
4. 板块退潮：所属板块强度跌出后 40% 分位且持仓收益转弱。
5. 持有超时：持仓超过 `max_hold_days`（默认 40）且分数低于中位数。

---

## 6. 每日全市场扫描流程（回测主循环）

对交易日历中的每个开市日 `T`：

1. 读取 `T` 日可用行情、指标、板块与市场状态数据。
2. 执行股票池过滤。
3. 计算四类因子分数与综合分数。
4. 对当前持仓先生成卖出信号。
5. 按资金约束和风控上限生成买入列表。
6. 输出 `T` 日信号表：
- `ts_code`
- `signal` (`BUY`/`SELL`/`HOLD`)
- `score`
- `target_weight`
- `target_amount`
- `reason_codes`

执行假设：`T` 日信号在 `T+1` 开盘成交。

---

## 7. 资金分配与仓位管理（100万人民币）

## 7.1 总仓位（随市场状态）

1. `RiskOn`：总仓位上限 90%
2. `Neutral`：总仓位上限 60%
3. `RiskOff`：总仓位上限 30%

## 7.2 单票仓位

建议约束：

1. 单票目标仓位区间：`5% ~ 12%`
2. 单行业上限：`30%`
3. 持仓数目标：
- RiskOn：10-14 只
- Neutral：6-10 只
- RiskOff：3-6 只

## 7.3 头寸计算（建议）

1. 先按分数分配权重：
- `raw_weight_i = score_i / sum(score_selected)`

2. 再做约束裁剪：
- `weight_i = clip(raw_weight_i * gross_exposure, min_w, max_w)`

3. 风险预算校正（ATR）：
- 每笔最大风险 `1%` 资金（1万元）
- `shares_by_risk = risk_budget / (2 * ATR)`
- 最终股数取 `min(shares_by_weight, shares_by_risk)` 并按 100 股取整。

## 7.4 交易成本与滑点（回测必须）

默认参数（可配置）：

1. 佣金：万 3（双边），最低 5 元。
2. 印花税：卖出 0.1%。
3. 过户费：按交易所规则配置（可先简化）。
4. 滑点：双边各 5 bps（可按成交额分层）。

---

## 8. 回测输出数据结构设计

建议新增以下集合/表（MongoDB 或 DuckDB 均可，推荐 MongoDB 便于 API 输出）：

## 8.1 `backtest_runs`

记录一次回测任务元信息：

1. `run_id`
2. `strategy_name`
3. `params`
4. `start_date`, `end_date`
5. `initial_capital`
6. `created_at`, `status`

## 8.2 `backtest_nav_daily`

每日净值与风控轨迹：

1. `run_id`, `trade_date`
2. `nav`, `cash`, `position_value`
3. `daily_return`, `cum_return`
4. `drawdown`, `exposure`
5. `benchmark_nav`（如沪深300）

## 8.3 `backtest_trades`

逐笔成交明细：

1. `run_id`, `trade_date`, `ts_code`
2. `side` (`BUY`/`SELL`)
3. `price`, `shares`, `amount`
4. `fee`, `slippage_cost`
5. `reason_codes`
6. `signal_score`

## 8.4 `backtest_positions_daily`

每日持仓快照：

1. `run_id`, `trade_date`, `ts_code`
2. `shares`, `cost_price`, `market_price`
3. `market_value`, `pnl`, `weight`
4. `holding_days`

## 8.5 `backtest_signals_daily`

每日全量扫描信号（可选，便于复盘）：

1. `run_id`, `trade_date`, `ts_code`
2. `signal`, `score`
3. `target_weight`, `target_amount`
4. `factor_breakdown`（json）

---

## 9. 回测指标（页面展示）

必备指标：

1. 累计收益率
2. 年化收益率
3. 最大回撤
4. 夏普比率（无风险利率默认 0）
5. 胜率
6. 盈亏比（Profit Factor）
7. 年化换手率
8. 平均持仓天数

---

## 10. 前端展示需求（回测页面）

## 10.1 图表

1. 净值曲线（策略 vs 基准）
2. 回撤曲线（面积图）
3. 仓位利用率曲线
4. 买卖操作标记：
- 在净值图上标记“净买入日/净卖出日”
- 点击日期可查看当日交易明细

## 10.2 表格

1. 交易明细表（可按股票/日期过滤）
2. 持仓变动表
3. 指标汇总卡片（收益、回撤、夏普等）

## 10.3 个股复盘联动（建议）

从交易明细点击股票可跳转个股 K 线页并带回测买卖点叠加。

---

## 11. 默认参数建议（首版）

1. `buy_threshold`: 75
2. `sell_threshold`: 50（用于弱化持仓淘汰）
3. `stop_loss_pct`: 0.08
4. `trail_stop_pct`: 0.10
5. `max_hold_days`: 40
6. `min_avg_amount_20d`: 30000000
7. `single_position_min`: 0.05
8. `single_position_max`: 0.12
9. `sector_max`: 0.30
10. `risk_per_trade`: 0.01
11. `slippage_bps`: 5

---

## 12. 回归测试与稳定性验证（Regression）

为保证策略可迭代，建议固定以下回归集：

1. 时间分段回测：
- 2010-2015
- 2016-2019
- 2020-2022
- 2023-2026

2. 市场状态覆盖：
- 单边牛市、震荡市、下跌市分别统计指标。

3. 稳定性阈值（示例）：
- 最大回撤不得劣化超过上版 +20%
- 夏普不得低于上版 -0.2
- 交易次数变化不超过 ±30%（参数未变场景）

---

## 13. 实施优先级（不含开发）

1. `MVP`：
- 市场状态 + 板块趋势 + 个股趋势
- 固定仓位法（先不启用 ATR 风险预算）
- 回测曲线 + 交易明细 + 最大回撤

2. `V2`：
- 加入估值/流动性代理因子
- 加入 ATR 风险预算仓位
- 完整绩效分析（夏普、盈亏比、分年收益）

3. `V3`：
- 因子权重自动调参
- 多策略组合（稳健/进攻）并行回测

---

## 14. 关键结论

在当前数据条件下，可以落地一个可解释、可回测、可视化完整的日频全市场选股系统。  
核心是先建立“市场风控 + 板块趋势 + 个股趋势”的主干框架，再逐步增强基本面代理因子和资金分配精细化逻辑。
