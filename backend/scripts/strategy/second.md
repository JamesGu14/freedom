# second.py 策略概要

## 策略类型

日频“上涨初期突破捕获”策略：在底部盘整后首次放量突破的第 1–3 天给出 BUY，避免追高。

## 数据输入

必需列（可通过 colmap 映射）：

- open, high, low, close
- volume
- macd_dif, macd_dea
- rsi

## 默认参数

- base_lookback = 30
- breakout_lookback = 20
- ma_fast = 5
- ma_mid = 10
- ma_slow = 20
- ma_trend = 60
- vol_ma = 5
- vol_ratio_th = 1.8
- body_ratio_th = 0.6
- rsi_regime = 50
- cooldown_days = 5
- extreme_move_pct = 0.09

## 计算流程

### 1) 均线与斜率

- 计算 MA5/10/20/60 与 MA20 斜率（MA20 - MA20.shift(1)）。

### 2) 底部/平台判定（近 base_lookback，满足 ≥2 条）

- 波动收敛：
  - (high.rolling(N).max() - low.rolling(N).min()) / close <= 0.35
- 均线粘合：
  - |MA5 - MA10| / close < 0.03 且 |MA10 - MA20| / close < 0.05
- 未大涨过滤：
  - close / low.rolling(N).min() <= 1.6

### 3) 首次有效突破（BUY 核心）

- HH = high.rolling(breakout_lookback).max().shift(1)
- 首次条件：close.shift(1) <= HH.shift(1)
- 突破条件全部满足：
  - close > HH
  - 阳线且实体强：(close - open) / (high - low) >= body_ratio_th
  - 放量：volume >= vol_ratio_th * volume.rolling(vol_ma).mean()

### 4) 动能确认（满足 ≥1）

- MACD 金叉翻正：dif > dea 且 dif.shift(1) <= dea.shift(1) 且 (dif-dea) > 0
- RSI 上穿 50：rsi > 50 且 rsi.shift(1) <= 50
- 均线多头：MA5 > MA10 > MA20 且 MA20 斜率 > 0

### 5) BUY 信号

当日 BUY 当且仅当：

- 平台条件 ≥2
- 首次有效突破成立
- 动能确认 ≥1
- 不在冷却期
- 当日涨跌幅未超过 extreme_move_pct

### 6) SELL 信号（任一触发）

- close < MA20 且 MA20 斜率 < 0
- MACD 死叉且在 0 轴上方
- 放量长阴破位：close < open 且 volume > 1.5 * vol_ma5 且 close < low.shift(1)
- 突破失败保护：买入后 10 日内 close < breakout_price

### 7) HOLD

- 不满足 BUY / SELL
- 或极端波动日：abs(close.pct_change()) >= extreme_move_pct

### 8) 冷却期

- BUY/SELL 分开冷却
- cooldown_days 内相同信号只允许一次（基于最终 signal）

## 输出

- `predict_date(date)` 返回 BUY / SELL / HOLD
- 日期不存在抛 KeyError
- 关键字段 NaN 时返回 HOLD
