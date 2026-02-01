# Daily Tasks

## 1) Pull daily market data (K-line)

```bash
python backend/scripts/daily/pull_daily_history.py
```

Optional ranges:

```bash
python backend/scripts/daily/pull_daily_history.py --last-days 7
python backend/scripts/daily/pull_daily_history.py --start-date 20240101 --end-date 20240131
```

## 2) Calculate indicators

```bash
python backend/scripts/one_time/calculate_indicators.py
```

## 3) Calculate daily signals

计算指定日期的交易信号（BUY信号）并存储到MongoDB。

```bash
# 计算今天的信号（日期格式：YYYYMMDD 或 YYYY-MM-DD）
python backend/scripts/daily/calculate_signal.py --given-date 20250126
# 或
python backend/scripts/daily/calculate_signal.py --given-date 2025-01-25
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
