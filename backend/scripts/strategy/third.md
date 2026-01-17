# third.py 策略概要

## 策略类型
日频三分类信号模型（BUY / SELL / HOLD），基于趋势过滤 + 多指标打分 + 风险过滤 + 冷却期。

## 数据来源
默认从 DuckDB 读取并合并：
- 日线行情（daily）
- 日线基础（daily_basic）
- 技术指标（indicators）

输入字段（合并后要求）：
- date, open, high, low, close, volume
- macd_dif, macd_dea
- kdj_k, kdj_d
- rsi

## 主要参数（默认值）
- ma_window = 20
- vol_ma_window = 5
- cooldown_days = 3
- extreme_move_pct = 0.08
- require_min_positive = 2
- require_min_negative = 2
- buy_threshold = 2.0
- sell_threshold = -2.0
- range_extra_strict = True
- range_threshold_bump = 0.5

## 计算流程

### 1) 趋势判定（第一层过滤）
- 计算 MA 与 MA 斜率：
  - ma = close.rolling(ma_window).mean()
  - ma_slope = ma - ma.shift(1)
- 趋势状态：
  - UP: close > ma 且 ma_slope > 0
  - DOWN: close < ma 且 ma_slope < 0
  - 其他为 RANGE
- 若 RANGE 且 range_extra_strict=True，则买卖阈值分别提高/降低 range_threshold_bump。

### 2) 指标打分（第二层）
每个指标输出 -1, -0.5, 0, +0.5, +1：

- MACD（金叉/死叉 + DIF/DEA 位置）：
  - cross_up 且 dif/dea < 0 → +1
  - cross_up 且 dif/dea > 0 → +0.5
  - cross_down 且 dif/dea > 0 → -1
  - cross_down 且 dif/dea < 0 → -0.5

- KDJ（金叉/死叉 + K 区间）：
  - cross_up 且 K < 30 → +1
  - cross_up 且 30 ≤ K < 50 → +0.5
  - cross_down 且 K > 70 → -1
  - cross_down 且 50 < K ≤ 70 → -0.5

- RSI（拐头 + 区间）：
  - RSI < 30 且上拐 → +1
  - 30 ≤ RSI < 50 且上行 → +0.5
  - RSI > 70 且下拐 → -1
  - 50 < RSI ≤ 70 且下行 → -0.5

- 量价确认：
  - 成交量 > 均量 且收盘上涨 → +1
  - 成交量 > 均量 且收盘下跌 → -1

### 3) 信号裁决（第三层）
- score_total = 各指标得分之和
- pos_cnt / neg_cnt 为正/负得分指标数
- 若正负同时 ≥2 → HOLD
- 否则：
  - score_total ≥ buy_th 且 pos_cnt ≥ require_min_positive → BUY
  - score_total ≤ sell_th 且 neg_cnt ≥ require_min_negative → SELL
  - 其他 → HOLD

### 4) 趋势过滤
- UP 趋势下不允许 SELL
- DOWN 趋势下不允许 BUY

### 5) 极端波动保护
- 若 |close.pct_change()| ≥ extreme_move_pct → 当日强制 HOLD

### 6) 冷却期
- BUY/SELL 分开计算
- 若过去 cooldown_days 内已出现相同信号，则当日改为 HOLD

## 输出
- `predict_date(date)` 返回 BUY / SELL / HOLD
- 日期不存在则抛 KeyError
- 指标缺失时按 HOLD 处理

## 备注
- 模型初始化时一次性预计算所有中间列，适合回测时逐日调用。
- 支持 `get_features(date)` 查看当日得分与信号细节。
