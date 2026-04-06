# multifactor_v1_low_freq_v3_sector_leader

目标：在 `252` 交易日窗口内将交易控制在 `<=100` 笔（本版设为 `<=96` 预留缓冲），并提升相对中证500的超额收益概率。

## 结合既有版本的归纳

- v1（低频初版）主打日内节流，但仍允许轮动，容易在高波动阶段产生额外换手。
- v2（硬约束版）加入了年化交易上限与质量过滤，方向正确，但把 `score_direction` 切到 `normal` 之后，容易偏离当前因子有效方向。
- 本地因子有效性日志（`logs/factor_analysis/summary_compare_multifactor_v1_20250101_20260206.json`）显示：
  - `normal`：`mean_rank_ic=-0.0330`，`long_short_cum_return=-0.3407`
  - `reverse`：`mean_rank_ic=+0.0330`，`long_short_cum_return=+0.4691`
- 因此 v3 恢复 `score_direction=reverse`，并强化“近期强势板块优先”。

## v3 关键变化

- 低频硬约束（更保守）
  - `max_annual_trade_count=96`
  - `max_annual_buy_count=48`
  - `max_annual_sell_count=48`
  - `max_daily_buy_count=1`, `max_daily_trade_count=2`
  - `max_daily_rotate_count=0`, `reentry_cooldown_days=20`
- 强势题材优先（你提出的核心要求）
  - `factor_weights.sector_strength=0.38`（总分里提高板块强度权重）
  - `entry_min_sector_strength=62`
  - `entry_sector_strength_quantile=0.72`（仅保留当日板块强度前约 28% 的候选）
  - 成分映射继续优先申万/中信：`use_member_sector_mapping=true`
- 入场质量与风控
  - `entry_require_trend_alignment=true`
  - `entry_require_macd_positive=true`
  - `entry_rsi_min=50`, `entry_rsi_max=72`, `entry_max_pct_chg=5.8`
  - `stop_loss_pct=0.075`, `trail_stop_pct=0.11`, `sell_confirm_days=2`

## 使用方式

1. 在策略中心创建新版本，`params_snapshot` 使用同目录 JSON。
2. 用与你当前不满意版本相同区间发起回测。
3. 重点验收：
   - 频率：`trade_count` 与 252 日滚动窗口交易数（目标 `<=100`）
   - 相对收益：净值曲线是否持续跑赢 `000905.SH`（中证500）
   - 稳定性：`win_rate`、年度回撤、风险态仓位控制

## 若仍未稳定跑赢中证500的调参顺序

1. 先加严买入质量：`buy_threshold 84 -> 86`。
2. 再收紧强势板块范围：`entry_sector_strength_quantile 0.72 -> 0.78`。
3. 若收益不足再小幅放宽频率：`max_annual_trade_count 96 -> 104`（同步盯回撤）。
