# multifactor_v1_low_freq_v1

目标：在尽量减少日频操作次数的前提下，保持并提升收益质量。

## 关键变化

- 板块强度映射：优先按申万/中信成分关系映射到个股，再回退到 `stock_basic.industry` 文本映射。
- 日内节流：
  - `max_daily_buy_count=2`
  - `max_daily_sell_count=4`
  - `max_daily_trade_count=4`
  - `max_daily_rotate_count=1`
  - `reentry_cooldown_days=10`
- 降频增效参数：
  - `buy_threshold=78`
  - `sell_confirm_days=2`
  - `rotate_score_delta=12`
  - `rotate_profit_ceiling=0.01`
  - `min_hold_days_before_rotate=7`
  - `max_hold_days=60`

## 使用方式

1. 先创建一个新的 strategy version（`params_snapshot` 使用同目录 JSON 文件内容）。
2. 用新 version 发起回测，和当前满意的版本做 `run_id` 对比：
   - 收益：`total_return` / `annual_returns`
   - 风险：`annual_max_drawdowns`
   - 频率：`trade_count`、日均交易笔数、`BUY_ROTATE/SELL_ROTATE` 占比
