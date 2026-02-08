# 重构需求：大盘指数页面 K 线图展示

## 1. 背景与目标

### 1.1 现状

当前 `/market-index` 页面布局：

| 区域 | 内容 | 展示方式 |
|------|------|---------|
| 顶部 | 7 个指数概览卡片（上证、深证、创业板、沪深300、中证500、中证1000、科创50） | 可点击切换，显示涨跌幅/PE/PB/换手率 |
| 中部 | 指标序列（选中指数的近 120 交易日数据） | **表格**：交易日、涨跌幅、PE、PB、换手率、MACD、RSI6、KDJ |
| 底部 | 专业指数因子（近 60 条） | **表格**：交易日、涨跌幅、MACD、DIF、DEA、RSI6/12/24、WR10、CCI |

**问题**：表格无法直观展现趋势走势，不便于量化分析人员快速判断市场状态。

### 1.2 目标

将底部的"专业指数因子"表格替换为 **ECharts K 线图**（含多个技术指标子图），实现与个股页面 `/stocks/[ts_code]` 相似的可视化体验。

**改造后布局**：

| 区域 | 内容 | 展示方式 |
|------|------|---------|
| 顶部 | 7 个指数概览卡片 | **保持不变** |
| 中部 | 指标序列表 | **保持不变**（可点击行高亮对应日期） |
| 底部 | K 线图 + 技术指标子图 | **替换原表格**，跟随顶部卡片切换加载对应指数 |

---

## 2. 数据源分析

### 2.1 已有数据（MongoDB）

K 线图所需的全部数据均已存在于 MongoDB 中，**无需新增数据同步**。

| 集合 | 可用字段 | 用途 |
|------|---------|------|
| `index_factor_pro` | `open`, `high`, `low`, `close`, `vol`, `amount` | K 线主图 OHLCV |
| `index_factor_pro` | `ma_bfq_5`, `ma_bfq_10`, `ma_bfq_20`, `ma_bfq_60` | MA 均线叠加 |
| `index_factor_pro` | `macd_dif_bfq`, `macd_dea_bfq`, `macd_bfq` | MACD 子图 |
| `index_factor_pro` | `kdj_k_bfq`, `kdj_d_bfq`, `kdj_bfq` | KDJ 子图 |
| `index_factor_pro` | `rsi_bfq_6`, `rsi_bfq_12`, `rsi_bfq_24` | RSI 子图 |
| `index_factor_pro` | `boll_upper_bfq`, `boll_mid_bfq`, `boll_lower_bfq` | BOLL（可选叠加主图） |
| `market_index_dailybasic` | `pe`, `pb` | PE/PB 估值子图 |

### 2.2 字段名注意事项

`idx_factor_pro` API 返回的技术指标字段带 `_bfq` 后缀（指数不涉及复权，只有不复权版本）：

| 用途 | API/MongoDB 字段名 | 说明 |
|------|-------------------|------|
| K 线 | `open`, `high`, `low`, `close` | 无后缀 |
| 成交量 | `vol` | 无后缀（手） |
| 涨跌幅 | `pct_change` | 无后缀 |
| MA | `ma_bfq_5`, `ma_bfq_10`, `ma_bfq_20`, `ma_bfq_60`, `ma_bfq_90`, `ma_bfq_250` | `_bfq` 后缀 |
| MACD | `macd_dif_bfq`（DIF）, `macd_dea_bfq`（DEA）, `macd_bfq`（柱状图） | `_bfq` 后缀 |
| KDJ | `kdj_k_bfq`, `kdj_d_bfq`, `kdj_bfq`（J 线） | `_bfq` 后缀 |
| RSI | `rsi_bfq_6`, `rsi_bfq_12`, `rsi_bfq_24` | `_bfq` 后缀 |
| BOLL | `boll_upper_bfq`, `boll_mid_bfq`, `boll_lower_bfq` | `_bfq` 后缀 |

> **重要**：当前 `mongo_market_index.py` 中 `get_market_index_series()` 的 projection 使用了不带 `_bfq` 后缀的字段名（如 `macd`, `kdj_k`），可能导致查询结果为 null。此次重构需一并修复。

---

## 3. K 线图设计（量化交易视角）

### 3.1 图表整体布局

采用 6 个子图垂直排列，通过 DataZoom 联动，实现多维度同步分析：

```
┌─────────────────────────────────────────────┐
│  Grid 0: K 线主图 + MA 均线                    │  height: 300px
│  （蜡烛图 + MA5/MA10/MA20/MA60）               │
├─────────────────────────────────────────────┤
│  Grid 1: 成交量                               │  height: 80px
├─────────────────────────────────────────────┤
│  Grid 2: MACD                               │  height: 140px
│  （DIF + DEA + 柱状图）                        │
├─────────────────────────────────────────────┤
│  Grid 3: KDJ                                │  height: 140px
│  （K + D + J 三线）                            │
├─────────────────────────────────────────────┤
│  Grid 4: RSI                                │  height: 140px
│  （RSI6 + RSI12 + RSI24 三线）                 │
├─────────────────────────────────────────────┤
│  Grid 5: PE / PB 估值趋势                     │  height: 140px
│  （PE 左轴 + PB 右轴，双 Y 轴）                │
├─────────────────────────────────────────────┤
│  DataZoom 滑块                               │  height: 25px
└─────────────────────────────────────────────┘
```

**总高度**：约 1050px（可按屏幕自适应）

### 3.2 各子图详细设计

#### Grid 0: K 线主图

| 元素 | 类型 | 颜色 | 说明 |
|------|------|------|------|
| K 线 | candlestick | 红涨（#ef4444）/ 绿跌（#22c55e） | 标准 OHLC 蜡烛图 |
| MA5 | line | 白色 | 短期均线 |
| MA10 | line | 粉色（#ff69b4） | |
| MA20 | line | 黄色（#ffff00） | 中期均线 |
| MA60 | line | 蓝色（#4169e1） | 中长期均线 |

- `scale: true` 自适应缩放
- tooltip 显示：日期、开高低收、涨跌幅、各 MA 值

#### Grid 1: 成交量

| 元素 | 类型 | 颜色 | 说明 |
|------|------|------|------|
| 成交量 | bar | 红涨 / 绿跌（跟随 K 线方向） | 收盘 ≥ 开盘为红，否则为绿 |

#### Grid 2: MACD

| 元素 | 类型 | 颜色 | 说明 |
|------|------|------|------|
| DIF | line | 蓝色（#4169e1） | 快线 |
| DEA | line | 粉色（#ff69b4） | 慢线 |
| MACD 柱 | bar | 绿正（#22c55e）/ 红负（#ef4444） | 柱状图 |

- 零轴参考线

#### Grid 3: KDJ

| 元素 | 类型 | 颜色 | 说明 |
|------|------|------|------|
| K | line | 粉色（#ff69b4） | |
| D | line | 蓝色（#4169e1） | |
| J | line | 黄色（#ffff00） | |

- 参考线：20/50/80 三条水平线（超买超卖区域）

#### Grid 4: RSI

| 元素 | 类型 | 颜色 | 说明 |
|------|------|------|------|
| RSI6 | line | 粉色（#ff69b4） | 短周期 |
| RSI12 | line | 蓝色（#4169e1） | 中周期 |
| RSI24 | line | 黄色（#ffff00） | 长周期 |

- 参考线：30/70 两条水平线（超买超卖分界）
- RSI 范围固定 0–100

#### Grid 5: PE / PB 估值趋势

| 元素 | 类型 | 颜色 | Y 轴 | 说明 |
|------|------|------|------|------|
| PE (TTM) | line | 橙色（#f59e0b） | 左轴 | 市盈率趋势 |
| PB | line | 青色（#06b6d4） | 右轴 | 市净率趋势 |

- 双 Y 轴：PE 和 PB 数量级不同，需各自缩放
- 数据来源：`market_index_dailybasic` 集合（按 trade_date 与 K 线对齐）

### 3.3 交互设计

| 交互 | 行为 |
|------|------|
| 概览卡片点击 | 切换指数 → 更新序列表 + K 线图 |
| DataZoom 滑块/滚轮 | 6 个子图联动缩放 |
| 鼠标悬停 | 跨子图十字线联动，tooltip 显示所有指标值 |
| 默认范围 | 显示最近 120 个交易日 |
| 数据量 | 一次加载最近 500 个交易日（约 2 年），DataZoom 控制可见范围 |

---

## 4. 改动清单

### 4.1 后端 API 改动

#### 4.1.1 新增/修改端点：`GET /api/market-index/chart`

新增专用端点，返回 K 线图所需的全部数据（OHLCV + 技术指标 + 估值），一次请求获取全部数据，减少前端并发。

**请求参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `ts_code` | str | 是 | 指数代码（如 `000300.SH`） |
| `limit` | int | 否 | 返回条数（默认 500，最大 2000） |

**返回结构**：

```json
{
  "ts_code": "000300.SH",
  "items": [
    {
      "trade_date": "20260202",
      "open": 3500.12,
      "high": 3520.88,
      "low": 3490.33,
      "close": 3515.66,
      "vol": 12345678.0,
      "pct_change": 0.83,
      "ma5": 3510.22,
      "ma10": 3505.11,
      "ma20": 3498.00,
      "ma60": 3480.55,
      "macd_dif": 12.31,
      "macd_dea": 10.22,
      "macd": 4.18,
      "kdj_k": 72.5,
      "kdj_d": 65.3,
      "kdj_j": 86.9,
      "rsi6": 58.66,
      "rsi12": 55.12,
      "rsi24": 50.09,
      "pe": 14.71,
      "pb": 1.52
    }
  ],
  "total": 500
}
```

> 注意：返回的字段名使用简化名称（不带 `_bfq` 后缀），后端负责从 MongoDB 映射。

**后端实现要点**：

```python
# 字段映射：MongoDB 原始字段 → API 返回字段
FACTOR_FIELD_MAP = {
    "ma_bfq_5": "ma5",
    "ma_bfq_10": "ma10",
    "ma_bfq_20": "ma20",
    "ma_bfq_60": "ma60",
    "macd_dif_bfq": "macd_dif",
    "macd_dea_bfq": "macd_dea",
    "macd_bfq": "macd",
    "kdj_k_bfq": "kdj_k",
    "kdj_d_bfq": "kdj_d",
    "kdj_bfq": "kdj_j",
    "rsi_bfq_6": "rsi6",
    "rsi_bfq_12": "rsi12",
    "rsi_bfq_24": "rsi24",
}

# 查询 index_factor_pro（OHLCV + 技术指标）
# 查询 market_index_dailybasic（PE/PB）
# 按 trade_date 合并两个集合的数据
# 重命名字段后返回
```

#### 4.1.2 修复现有 series 端点

当前 `get_market_index_series()` 中的 projection 使用了不带 `_bfq` 的字段名，需修复为正确的 MongoDB 字段名。

**文件**：`backend/app/data/mongo_market_index.py`

```python
# 修复前（可能查不到数据）
projection_factor = {
    "macd": 1,
    "macd_dif": 1,
    "kdj_k": 1,
    "rsi_6": 1,
    ...
}

# 修复后
projection_factor = {
    "macd_bfq": 1,
    "macd_dif_bfq": 1,
    "kdj_k_bfq": 1,
    "rsi_bfq_6": 1,
    ...
}
```

同时在返回时做字段重命名，保持 API 对外接口不变。

### 4.2 前端改动

#### 4.2.1 页面改造（`frontend/pages/market-index.js`）

**主要改动**：

1. **移除**底部"专业指数因子"表格 section
2. **新增** K 线图 section（使用 ECharts dynamic import，参考 `stocks/[ts_code].js`）
3. **新增** `loadChart` 函数，调用 `/api/market-index/chart` 端点
4. **联动**：当 `selectedCode` 变化时，同时更新序列表和 K 线图

**数据流**：

```
点击概览卡片 → setSelectedCode
  ├─→ loadDetail()  → 更新中部序列表
  └─→ loadChart()   → 更新底部 K 线图
```

#### 4.2.2 ECharts 配置

从 `stocks/[ts_code].js` 复用 K 线图配置逻辑，主要差异：

| 对比项 | 个股页面 | 指数页面 |
|--------|---------|---------|
| 子图数量 | 4 个（K 线、成交量、KDJ、MACD） | 6 个（+ RSI、PE/PB） |
| MA 周期 | MA5/10/20/30 | MA5/10/20/60 |
| RSI | 不展示 | RSI6/12/24 三线 |
| 估值 | 不展示 | PE/PB 双 Y 轴 |
| 数据来源 | DuckDB Parquet | MongoDB |
| 图表高度 | ~880px | ~1050px |

**建议**：将 K 线图渲染逻辑提取为可复用的工具函数/组件（可选，本次不强制要求）。

#### 4.2.3 样式新增

```css
/* K 线图容器 */
.market-chart-container {
  width: 100%;
  height: 1050px;
  background: #1a1a2e;
  border-radius: 8px;
  margin-top: 16px;
}

/* 图表标题栏 */
.chart-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
}
```

---

## 5. 开发检查清单

### 阶段 1: 后端 API
- [ ] 新增 `GET /api/market-index/chart` 端点
  - [ ] 查询 `index_factor_pro`（OHLCV + 技术指标）
  - [ ] 查询 `market_index_dailybasic`（PE/PB）
  - [ ] 按 `trade_date` 合并两个数据源
  - [ ] 字段重命名（`_bfq` 后缀 → 简化名称）
- [ ] 修复 `get_market_index_series()` 中的字段名问题

### 阶段 2: 前端 K 线图
- [ ] 移除底部"专业指数因子"表格
- [ ] 新增 ECharts K 线图 section
  - [ ] Grid 0: K 线 + MA 均线
  - [ ] Grid 1: 成交量柱状图
  - [ ] Grid 2: MACD（DIF + DEA + 柱状图）
  - [ ] Grid 3: KDJ（K + D + J）
  - [ ] Grid 4: RSI（6 + 12 + 24）
  - [ ] Grid 5: PE/PB 估值趋势（双 Y 轴）
- [ ] DataZoom 联动（6 个子图同步）
- [ ] Tooltip 十字线联动
- [ ] 概览卡片切换 → K 线图联动更新
- [ ] 图表 resize 处理 + cleanup

### 阶段 3: 样式与优化
- [ ] 深色主题样式适配
- [ ] 加载状态 / 空数据提示
- [ ] 默认显示最近 120 交易日

---

## 6. 设计考量（量化交易视角）

### 6.1 为什么选择 6 个子图

作为量化分析师，日常看盘需要同时关注：

1. **价格走势**（K 线 + MA）：判断趋势方向和支撑阻力位
2. **量能**（成交量）：确认趋势的有效性
3. **MACD**：中长期趋势动量，金叉/死叉信号
4. **KDJ**：超买超卖判断，短期转折点
5. **RSI**：多周期（6/12/24）共振判断，比单一 RSI 更可靠
6. **估值**（PE/PB）：指数独有维度，判断整体市场估值水平是否合理

> 个股页面不需要 PE/PB 子图（单股估值波动大意义有限），但指数估值趋势是非常重要的宏观参考。

### 6.2 为什么 RSI 用三线

指数不像个股波动剧烈，RSI(14) 单线容易长期在 40-60 区间震荡缺乏信号。三线（6/12/24）可以通过：
- **短期 RSI6 穿越 RSI12**：确认短线拐点
- **RSI24 作为趋势基准**：判断多空大方向
- **三线共振**：三线同时进入超买/超卖区域时信号更可靠

### 6.3 PE/PB 双 Y 轴设计

PE 通常在 10-30 范围，PB 通常在 1-3 范围，数量级差异较大，必须用双 Y 轴。左轴 PE、右轴 PB，各自独立缩放。

---

## 7. 未来可选优化

以下功能本次不实现，留作后续迭代：

| 优化项 | 说明 |
|--------|------|
| BOLL 带叠加 | 在 K 线主图叠加布林带上下轨 |
| 指标选择器 | 用户可自定义显示/隐藏哪些子图 |
| 多指数叠加 | 同一图表对比多个指数走势 |
| K 线图组件化 | 提取通用 K 线组件，个股页面也复用 |
| 周线/月线切换 | 切换不同周期的 K 线 |
