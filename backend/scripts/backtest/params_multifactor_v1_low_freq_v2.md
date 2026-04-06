# multifactor_v1_low_freq_v2

目标：在 252 个交易日内将总交易笔数硬约束在 100 笔以内，同时提升买入质量与胜率，争取超越中证500。

## 核心变化

- 交易频率硬约束（引擎级）
  - `annual_trade_window_days=252`
  - `max_annual_trade_count=100`
  - `max_annual_buy_count=50`
  - `max_annual_sell_count=50`
- 风险态禁买
  - `allow_buy_in_risk_off=false`
  - `market_exposure.risk_off=0.2`
  - `market_exposure_floor=0.2`
- 入场质量过滤（提胜率）
  - `entry_require_trend_alignment=true`（`close > ma20 > ma60`）
  - `entry_require_macd_positive=true`
  - `entry_min_sector_strength=55`
  - `entry_rsi_min=52`, `entry_rsi_max=75`
  - `entry_max_pct_chg=6.5`
- 低频化
  - `max_daily_buy_count=1`
  - `max_daily_sell_count=2`
  - `max_daily_trade_count=2`
  - `max_daily_rotate_count=0`
  - `reentry_cooldown_days=15`

## 使用方式

1. 在策略中心创建新版本，`params_snapshot` 使用同目录 JSON。
2. 跑与旧版同区间回测，对比：
   - 收益：`total_return`、年度收益
   - 相对基准：净值曲线与中证500对比
   - 频率：`trade_count` 与 252 日滚动窗口交易笔数
   - 质量：`win_rate`、最大回撤
3. 如果收益仍弱于中证500，优先调参顺序：
   - 提高 `buy_threshold`（82 -> 84）
   - 收紧 `entry_max_pct_chg`（6.5 -> 5.5）
   - 放宽 `max_annual_trade_count`（100 -> 110）并同步观察回撤
