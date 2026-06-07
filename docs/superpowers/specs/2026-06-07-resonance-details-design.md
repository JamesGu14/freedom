# 极强共振详情页 + 状态管理 设计文档

> 日期: 2026-06-07
> 项目: Freedom Quant Platform
> 作者: AI Assistant

---

## 1. 需求概述

在首页（`/`）的极强共振面板右上角增加"详情"按钮，点击后跳转到"极强详情"页面，展示该共振级别下所有股票的 K 线图，并支持对每只股票进行"忽略"和"认可"状态管理。

### 1.1 用户故事

- 作为交易者，我想查看极强共振股票的 K 线图详情，以便快速判断买卖时机
- 作为交易者，我想标记某些股票为"认可"，以便在首页优先关注它们
- 作为交易者，我想忽略某些不感兴趣的股票，以便减少干扰
- 作为交易者，我想筛选查看不同状态的股票，以便灵活管理关注列表

### 1.2 功能清单

| 功能 | 优先级 | 说明 |
|------|--------|------|
| 首页"详情"按钮 | P0 | 极强共振面板右上角 |
| 极强详情页 | P0 | 展示股票 K 线图列表 |
| 状态管理（忽略/认可） | P0 | 三态流转 |
| 筛选器 | P0 | 全部/只看认可/认可+未标记 |
| 首页高亮与排序 | P0 | 认可股票前置+高亮 |
| 信号重算保护 | P1 | 保留用户状态 |

---

## 2. 数据模型

### 2.1 现有模型

**集合**: `daily_stock_pattern_resonance`

```javascript
{
  "trade_date": "20250606",
  "signal_side": "buy",
  "resonance_level": "very_strong",
  "count": 25,
  "stocks": [
    {
      "ts_code": "000001.SZ",
      "name": "平安银行",
      "industry": "银行",
      "close": 12.50,
      "pct_chg": 2.35,
      "volume_ratio": 1.8,
      "weighted_score": 18,
      "patterns": ["ma_bullish_alignment", "golden_spider"]
      // ... 现有字段
    }
  ]
}
```

### 2.2 变更：增加 user_state 字段

在 `stocks[]` 数组的每个对象中增加 `user_state` 字段：

```javascript
{
  "ts_code": "000001.SZ",
  "name": "平安银行",
  // ... 现有字段 ...
  "user_state": null | "acknowledged" | "ignored"
}
```

**状态定义**:

| 状态值 | 显示名称 | 说明 |
|--------|----------|------|
| `null` | 未标记 | 默认状态 |
| `"acknowledged"` | 已认可 | 用户主动认可 |
| `"ignored"` | 已忽略 | 用户主动忽略 |

**状态流转**:

```
null --[点击"认可"]--> acknowledged
null --[点击"忽略"]--> ignored
acknowledged --[点击"取消认可"]--> null
acknowledged --[点击"忽略"]--> ignored
ignored --[点击"取消忽略"]--> null
ignored --[点击"认可"]--> acknowledged
```

**注意**: 由于 `daily_stock_pattern_resonance` 按 `(trade_date, signal_side, resonance_level)` 组合存储，`user_state` 也是绑定在这个组合上的。如果一只股票从 `very_strong` 降级到 `strong`，其 `user_state` 不会自动迁移（这是预期行为，因为不同共振级别是独立判断的）。

---

## 3. 后端 API 设计

### 3.1 新增 API

#### PUT /daily-stock-signals/resonance/state

更新股票在共振数据中的状态。

**请求体**:

```json
{
  "trade_date": "20250606",
  "ts_code": "000001.SZ",
  "signal_side": "buy",
  "resonance_level": "very_strong",
  "user_state": "acknowledged"
}
```

**参数说明**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| trade_date | string | 是 | 交易日期，YYYYMMDD |
| ts_code | string | 是 | 股票代码 |
| signal_side | string | 是 | "buy" 或 "sell" |
| resonance_level | string | 是 | "very_strong", "strong", "normal" |
| user_state | string | 是 | "acknowledged", "ignored", 或 null |

**响应**:

```json
{
  "success": true,
  "trade_date": "20250606",
  "ts_code": "000001.SZ",
  "user_state": "acknowledged"
}
```

**错误响应**:

```json
{
  "detail": "Stock not found in resonance group"
}
```

**实现逻辑**:

1. 验证参数完整性
2. 验证 `user_state` 值只能是 `"acknowledged"`、`"ignored"` 或 `null`
3. 查询 `daily_stock_pattern_resonance` 集合，匹配 `trade_date` + `signal_side` + `resonance_level`
4. 在 `stocks` 数组中找到匹配的 `ts_code`
5. 更新该股票的 `user_state` 字段
6. 使用 `$set` 定位更新，避免覆盖其他字段
7. 清除相关缓存（使用 `cache_delete_pattern`）

**MongoDB 更新语句**:

```javascript
db.daily_stock_pattern_resonance.updateOne(
  {
    trade_date: "20250606",
    signal_side: "buy",
    resonance_level: "very_strong",
    "stocks.ts_code": "000001.SZ"
  },
  {
    $set: { "stocks.$.user_state": "acknowledged" }
  }
)
```

### 3.2 修改现有 API

#### GET /daily-stock-signals/overview

**变更**: 返回的 `stocks` 数组中每个对象包含 `user_state` 字段（如果存在）。

**排序逻辑变更**:

在返回 `buy_resonance` 和 `sell_resonance` 之前，对每个 `stocks` 数组进行排序：

1. 首要排序：`user_state === "acknowledged"` 的股票排在最前面
2. 次要排序：保持原有排序（按 `weighted_score` 降序或原有顺序）

**实现代码**:

```python
def _sort_stocks_by_state(stocks):
    """认可的股票排在最前面"""
    return sorted(
        stocks,
        key=lambda s: (0 if s.get("user_state") == "acknowledged" else 1, -s.get("weighted_score", 0))
    )
```

**注意**: `_truncate_group_stocks` 函数（`daily_stock_signals_service.py` 第29-45行）需要更新以包含 `user_state` 字段，否则 overview 接口不会返回该字段。

#### GET /daily-stock-signals/stock/{ts_code}/patterns

**变更**: 返回结果中包含 `user_state` 字段。

**注意**: `get_stock_pattern_details` 函数需要更新以传递 `user_state`。

---

## 4. 前端设计

### 4.1 首页变更 (`/`)

#### ResonanceCard 组件

在卡片 header 右侧增加"详情"按钮（仅对 `very_strong` 级别显示）：

```jsx
const ResonanceCard = ({ group }) => (
  <section className="signal-card resonance-card">
    <div className="signal-card__header">
      <h3>{getResonanceLabel(group.resonance_level)}</h3>
      <div className="signal-card__header-right">
        <span className="signal-card__count">{group.count || 0} 只</span>
        {group.resonance_level === "very_strong" && group.count > 0 && (
          <Link 
            href={`/resonance-details?trade_date=${group.trade_date}&signal_side=${group.signal_side}&resonance_level=${group.resonance_level}`}
            className="resonance-detail-btn"
          >
            详情
          </Link>
        )}
      </div>
    </div>
    <StockList stocks={group.stocks || []} tradeDate={group.trade_date} />
  </section>
);
```

#### StockList 组件 - 排序与高亮

在 `StockList` 组件中，对传入的 `stocks` 进行排序和样式处理：

```jsx
const StockList = ({ stocks = [], tradeDate = "" }) => {
  // ... 现有代码 ...
  
  // 排序：认可的排在最前面
  const sortedStocks = useMemo(() => {
    return [...stocks].sort((a, b) => {
      const aAck = a.user_state === "acknowledged" ? 1 : 0;
      const bAck = b.user_state === "acknowledged" ? 1 : 0;
      if (aAck !== bAck) return bAck - aAck; // 认可的在前
      return 0; // 保持原有顺序
    });
  }, [stocks]);
  
  // 分页使用 sortedStocks
  const pageItems = sortedStocks.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  
  return (
    <div>
      <div className="signal-stock-grid">
        {pageItems.map((item) => (
          <div 
            key={item.ts_code} 
            className={`signal-stock-cell ${item.user_state === "acknowledged" ? "signal-stock-cell--acknowledged" : ""}`}
          >
            {/* ... 现有内容 ... */}
          </div>
        ))}
      </div>
    </div>
  );
};
```

**CSS 高亮样式**:

```css
.signal-stock-cell--acknowledged {
  border: 2px solid #f59e0b; /* 琥珀色边框 */
  background-color: rgba(245, 158, 11, 0.05); /* 淡琥珀色背景 */
}
```

### 4.2 新增页面：极强详情页 (`/resonance-details`)

#### 页面路由

文件: `frontend/pages/resonance-details.js`

#### URL 参数

| 参数 | 说明 | 示例 |
|------|------|------|
| trade_date | 交易日期 | 20250606 |
| signal_side | 信号方向 | buy / sell |
| resonance_level | 共振级别 | very_strong / strong / normal |

#### 页面布局

```
┌─────────────────────────────────────────────────────────────┐
│ 极强共振详情 · 2025-06-06 · 买入 · 极强共振 (14+)            │
│                                                             │
│ [全部] [只看认可] [认可+未标记]                              │
│                                                             │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ 000001.SZ 平安银行 · 银行 · 收盘 12.50 · +2.35%          │ │
│ │                                                         │ │
│ │ ┌─────────────────────────────────────────────────────┐ │ │
│ │ │                                                     │ │ │
│ │ │              [K 线图区域 - 300px 高度]               │ │ │
│ │ │                                                     │ │ │
│ │ │         显示最近 60 日 K 线 + MA5/MA10/MA20         │ │ │
│ │ │                                                     │ │ │
│ │ └─────────────────────────────────────────────────────┘ │ │
│ │                                                         │ │
│ │ [忽略] [认可]  ← 或 →  [取消忽略] [认可]                │ │
│ └─────────────────────────────────────────────────────────┘ │
│                                                             │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ 000002.SZ 万科A · 房地产 · 收盘 8.30 · -1.20%            │ │
│ │ ...                                                     │ │
│ └─────────────────────────────────────────────────────────┘ │
│                                                             │
│                    ‹ 上一页  1 / 5  下一页 ›                 │
└─────────────────────────────────────────────────────────────┘
```

#### 组件结构

```jsx
export default function ResonanceDetailsPage() {
  // URL 参数
  const { trade_date, signal_side, resonance_level } = router.query;
  
  // 状态
  const [stocks, setStocks] = useState([]);
  const [filter, setFilter] = useState("all"); // "all" | "acknowledged" | "active"
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  
  // 筛选逻辑
  const filteredStocks = useMemo(() => {
    switch (filter) {
      case "acknowledged":
        return stocks.filter(s => s.user_state === "acknowledged");
      case "active":
        return stocks.filter(s => s.user_state !== "ignored");
      case "all":
      default:
        return stocks;
    }
  }, [stocks, filter]);
  
  // 筛选切换时重置到第一页
  useEffect(() => {
    setPage(1);
  }, [filter]);
  
  // 分页
  const pageSize = 5;
  const totalPages = Math.max(Math.ceil(filteredStocks.length / pageSize), 1);
  const pageItems = filteredStocks.slice((page - 1) * pageSize, page * pageSize);
  
  // 状态更新（带错误回滚）
  const updateStockState = async (tsCode, newState) => {
    const previousState = stocks.find(s => s.ts_code === tsCode)?.user_state;
    
    // 乐观更新
    setStocks(prev => prev.map(s => 
      s.ts_code === tsCode ? { ...s, user_state: newState } : s
    ));
    
    try {
      const res = await apiFetch("/daily-stock-signals/resonance/state", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          trade_date,
          ts_code: tsCode,
          signal_side,
          resonance_level,
          user_state: newState,
        }),
      });
      
      if (!res.ok) {
        throw new Error(`更新失败: ${res.status}`);
      }
    } catch (err) {
      // 回滚到之前状态
      setStocks(prev => prev.map(s => 
        s.ts_code === tsCode ? { ...s, user_state: previousState } : s
      ));
      alert(err.message || "更新失败，请重试");
    }
  };
  
  // 加载共振数据
  useEffect(() => {
    if (!trade_date || !signal_side || !resonance_level) return;
    
    let cancelled = false;
    setLoading(true);
    
    apiFetch(`/daily-stock-signals/overview?trade_date=${trade_date}`)
      .then(async (res) => {
        if (!res.ok) throw new Error("加载失败");
        const data = await res.json();
        if (cancelled) return;
        
        // 找到匹配的共振组
        const resonanceGroups = signal_side === "buy" ? data.buy_resonance : data.sell_resonance;
        const group = resonanceGroups.find(g => g.resonance_level === resonance_level);
        
        if (group) {
          setStocks(group.stocks || []);
        } else {
          setStocks([]);
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    
    return () => { cancelled = true; };
  }, [trade_date, signal_side, resonance_level]);
  
  return (
    <main className="page">
      <header>...</header>
      
      {/* 筛选器 */}
      <div className="filter-tabs">
        <button className={filter === "all" ? "active" : ""} onClick={() => setFilter("all")}>
          全部 ({stocks.length})
        </button>
        <button className={filter === "acknowledged" ? "active" : ""} onClick={() => setFilter("acknowledged")}>
          只看认可 ({stocks.filter(s => s.user_state === "acknowledged").length})
        </button>
        <button className={filter === "active" ? "active" : ""} onClick={() => setFilter("active")}>
          认可+未标记 ({stocks.filter(s => s.user_state !== "ignored").length})
        </button>
      </div>
      
      {/* 股票列表 */}
      <div className="resonance-detail-list">
        {pageItems.map(stock => (
          <StockDetailCard 
            key={stock.ts_code} 
            stock={stock} 
            onUpdateState={updateStockState}
          />
        ))}
      </div>
      
      {/* 分页 */}
      {totalPages > 1 && <Pagination ... />}
    </main>
  );
}
```

#### StockDetailCard 组件

```jsx
function StockDetailCard({ stock, onUpdateState }) {
  const [candles, setCandles] = useState([]);
  const [chartLoading, setChartLoading] = useState(true);
  const [chartError, setChartError] = useState("");
  const chartRef = useRef(null);
  const chartInstanceRef = useRef(null);
  
  // 加载 K 线数据
  useEffect(() => {
    let cancelled = false;
    setChartLoading(true);
    setChartError("");
    
    apiFetch(`/stocks/${stock.ts_code}/candles?limit=60`)
      .then(async (res) => {
        if (!res.ok) throw new Error(`加载失败: ${res.status}`);
        const data = await res.json();
        if (!cancelled) setCandles(data.daily || []);
      })
      .catch((err) => {
        if (!cancelled) setChartError(err.message);
      })
      .finally(() => {
        if (!cancelled) setChartLoading(false);
      });
    
    return () => { cancelled = true; };
  }, [stock.ts_code]);
  
  // 渲染 ECharts
  useEffect(() => {
    if (!chartRef.current || !candles.length) return;
    
    // 清理旧实例
    if (chartInstanceRef.current) {
      chartInstanceRef.current.dispose();
    }
    
    const chart = echarts.init(chartRef.current);
    chartInstanceRef.current = chart;
    
    // 计算 MA
    const closes = candles.map(c => c.close);
    const ma5 = calculateMA(closes, 5);
    const ma10 = calculateMA(closes, 10);
    const ma20 = calculateMA(closes, 20);
    
    const option = {
      // ... ECharts 配置 ...
    };
    
    chart.setOption(option);
    
    return () => {
      chart.dispose();
      chartInstanceRef.current = null;
    };
  }, [candles]);
  
  const isAcknowledged = stock.user_state === "acknowledged";
  const isIgnored = stock.user_state === "ignored";
  
  return (
    <div className={`stock-detail-card ${isAcknowledged ? "acknowledged" : ""}`}>
      <div className="stock-detail-header">
        <h3>{stock.name} ({stock.ts_code})</h3>
        <span>{stock.industry}</span>
        <span>收盘 {stock.close}</span>
        <span className={stock.pct_chg > 0 ? "text-red" : "text-green"}>
          {stock.pct_chg}%
        </span>
      </div>
      
      {chartLoading && <div className="chart-loading">加载 K 线数据中...</div>}
      {chartError && <div className="chart-error">{chartError}</div>}
      <div ref={chartRef} className="stock-detail-chart" style={{ height: 300, display: chartLoading || chartError ? "none" : "block" }} />
      
      <div className="stock-detail-actions">
        {isIgnored ? (
          <>
            <button onClick={() => onUpdateState(stock.ts_code, null)}>取消忽略</button>
            <button onClick={() => onUpdateState(stock.ts_code, "acknowledged")}>认可</button>
          </>
        ) : isAcknowledged ? (
          <>
            <button onClick={() => onUpdateState(stock.ts_code, null)}>取消认可</button>
            <button onClick={() => onUpdateState(stock.ts_code, "ignored")}>忽略</button>
          </>
        ) : (
          <>
            <button onClick={() => onUpdateState(stock.ts_code, "ignored")}>忽略</button>
            <button onClick={() => onUpdateState(stock.ts_code, "acknowledged")}>认可</button>
          </>
        )}
      </div>
    </div>
  );
}

// 辅助函数：计算移动平均线
function calculateMA(data, period) {
  const result = [];
  for (let i = 0; i < data.length; i++) {
    if (i < period - 1) {
      result.push(null);
      continue;
    }
    let sum = 0;
    for (let j = 0; j < period; j++) {
      sum += data[i - j];
    }
    result.push(sum / period);
  }
  return result;
}
```

#### K 线图配置

复用现有 `StockKline` 页面的 ECharts 配置，但简化指标。MA 数据通过前端计算：

```javascript
// 辅助函数：计算移动平均线
function calculateMA(data, period) {
  const result = [];
  for (let i = 0; i < data.length; i++) {
    if (i < period - 1) {
      result.push(null);
      continue;
    }
    let sum = 0;
    for (let j = 0; j < period; j++) {
      sum += data[i - j];
    }
    result.push(sum / period);
  }
  return result;
}

// ECharts 配置
const option = {
  grid: { left: 50, right: 20, top: 20, bottom: 30 },
  xAxis: { type: "category", data: dates },
  yAxis: [
    { type: "value", scale: true },
    { type: "value", scale: true, splitLine: { show: false } }
  ],
  series: [
    {
      type: "candlestick",
      data: candleData,
      itemStyle: {
        color: "#ea3943",      // 涨 - 红色
        color0: "#00a650",     // 跌 - 绿色
        borderColor: "#ea3943",
        borderColor0: "#00a650"
      }
    },
    { name: "MA5", type: "line", data: ma5, smooth: true, lineStyle: { width: 1 } },
    { name: "MA10", type: "line", data: ma10, smooth: true, lineStyle: { width: 1 } },
    { name: "MA20", type: "line", data: ma20, smooth: true, lineStyle: { width: 1 } }
  ],
  tooltip: { trigger: "axis" }
};
```

### 4.3 筛选器组件

```jsx
function FilterTabs({ filter, onChange, counts }) {
  const tabs = [
    { key: "all", label: `全部 (${counts.all})` },
    { key: "acknowledged", label: `只看认可 (${counts.acknowledged})` },
    { key: "active", label: `认可+未标记 (${counts.active})` },
  ];
  
  return (
    <div className="filter-tabs">
      {tabs.map(tab => (
        <button
          key={tab.key}
          className={filter === tab.key ? "filter-tab active" : "filter-tab"}
          onClick={() => onChange(tab.key)}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
```

---

## 5. 信号重算保护

### 5.1 问题

`generate_daily_stock_signals.py` 或 `backfill_stock_signals.py` 脚本在重算信号时会重新生成 `daily_stock_pattern_resonance` 文档，覆盖现有数据。

### 5.2 解决方案

在脚本中，写入新数据前读取现有的 `user_state`，然后在写入时合并回去。

**实现代码**:

```python
def preserve_user_states(trade_date, signal_side, resonance_level, new_stocks):
    """保留现有 user_state 并在新数据中合并"""
    collection = get_collection("daily_stock_pattern_resonance")
    
    # 读取现有数据
    existing = collection.find_one(
        {"trade_date": trade_date, "signal_side": signal_side, "resonance_level": resonance_level},
        {"stocks.ts_code": 1, "stocks.user_state": 1}
    )
    
    if not existing:
        return new_stocks
    
    # 构建 ts_code -> user_state 映射
    state_map = {
        s["ts_code"]: s.get("user_state")
        for s in existing.get("stocks", [])
        if s.get("user_state") is not None
    }
    
    # 合并到新数据
    for stock in new_stocks:
        ts_code = stock.get("ts_code")
        if ts_code in state_map:
            stock["user_state"] = state_map[ts_code]
    
    return new_stocks
```

**在脚本中调用**:

```python
# 生成新的共振数据
new_stocks = calculate_resonance_stocks(...)

# 保留用户状态
new_stocks = preserve_user_states(trade_date, signal_side, resonance_level, new_stocks)

# 写入数据库
upsert_daily_stock_pattern_resonance([{
    "trade_date": trade_date,
    "signal_side": signal_side,
    "resonance_level": resonance_level,
    "stocks": new_stocks,
}])
```

---

## 6. 缓存策略

### 6.1 缓存清除

当用户更新状态时，需要清除相关缓存：

```python
def invalidate_signal_cache(trade_date):
    """清除信号相关缓存"""
    cache_delete_pattern(f"signals:overview:{trade_date}:*")
    cache_delete_pattern(f"signals:patterns:*:{trade_date}")
```

**注意**: 使用 `cache_delete_pattern` 而非 `cache_delete`，因为缓存 key 包含 `top_n` 参数（如 `signals:overview:20250606:50`）。

### 6.2 缓存更新

在 `PUT /daily-stock-signals/resonance/state` 接口中，更新数据库后调用 `invalidate_signal_cache`。

---

## 7. 样式设计

### 7.1 新增 CSS

```css
/* 首页 - 认可股票高亮 */
.signal-stock-cell--acknowledged {
  border: 2px solid #f59e0b;
  background-color: rgba(245, 158, 11, 0.05);
  box-shadow: 0 0 8px rgba(245, 158, 11, 0.2);
}

/* 详情页 - 股票卡片 */
.stock-detail-card {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 16px;
  background: var(--card-bg);
}

.stock-detail-card.acknowledged {
  border: 2px solid #f59e0b;
  background-color: rgba(245, 158, 11, 0.03);
}

.stock-detail-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.stock-detail-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.stock-detail-chart {
  width: 100%;
  border-radius: 4px;
  background: var(--chart-bg);
}

.stock-detail-actions {
  display: flex;
  gap: 8px;
  margin-top: 12px;
  justify-content: flex-end;
}

.stock-detail-actions button {
  padding: 6px 16px;
  border-radius: 4px;
  border: 1px solid var(--border);
  background: var(--btn-bg);
  cursor: pointer;
  font-size: 14px;
}

.stock-detail-actions button:hover {
  background: var(--btn-hover-bg);
}

.stock-detail-actions button:first-child {
  color: var(--muted);
}

.stock-detail-actions button:last-child {
  background: #f59e0b;
  color: white;
  border-color: #f59e0b;
}

.stock-detail-actions button:last-child:hover {
  background: #d97706;
}

/* 筛选器 */
.filter-tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border);
}

.filter-tab {
  padding: 8px 16px;
  border-radius: 4px;
  border: 1px solid var(--border);
  background: var(--btn-bg);
  cursor: pointer;
  font-size: 14px;
}

.filter-tab.active {
  background: var(--accent);
  color: white;
  border-color: var(--accent);
}

/* 详情按钮 */
.resonance-detail-btn {
  padding: 4px 12px;
  border-radius: 4px;
  background: var(--accent);
  color: white;
  text-decoration: none;
  font-size: 13px;
  margin-left: 8px;
}

.resonance-detail-btn:hover {
  background: var(--accent-dark);
}
```

---

## 8. 测试计划

### 8.1 单元测试

#### 后端

1. **状态更新 API 测试**
   - 正常更新状态（null → acknowledged）
   - 正常更新状态（null → ignored）
   - 切换状态（acknowledged → ignored）
   - 取消状态（acknowledged → null）
   - 错误情况：股票不在共振组中

2. **排序逻辑测试**
   - 认可的股票排在最前面
   - 同状态保持原有顺序

3. **信号重算保护测试**
   - 重算前读取 user_state
   - 重算后 user_state 保留
   - 新股票没有 user_state

#### 前端

1. **筛选器测试**
   - 全部筛选显示所有股票
   - 只看认可只显示 acknowledged
   - 认可+未标记排除 ignored

2. **状态按钮测试**
   - 未标记显示"忽略"和"认可"
   - 已认可显示"取消认可"和"忽略"
   - 已忽略显示"取消忽略"和"认可"

3. **分页测试**
   - 每页显示 5 只
   - 分页按钮正常工作

### 8.2 集成测试

1. 首页点击"详情"跳转到详情页
2. 详情页点击"认可"，回到首页该股票高亮且前置
3. 详情页点击"忽略"，筛选"认可+未标记"后该股票消失
4. 信号重算后，用户状态保留

---

## 9. 部署计划

### 9.1 数据库迁移

无需迁移，直接在新文档中增加字段即可。

### 9.2 部署步骤

1. 部署后端代码（新增 API + 修改现有 API）
2. 部署前端代码（新增页面 + 修改首页）
3. 更新信号重算脚本（保留 user_state）
4. 验证功能

### 9.3 回滚计划

1. 回滚后端代码
2. 回滚前端代码
3. 回滚脚本

---

## 10. 风险评估

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|----------|
| 信号重算覆盖 user_state | 高 | 高 | 修改脚本，重算前读取并合并 |
| 缓存不一致 | 中 | 中 | 更新状态时清除相关缓存 |
| 性能问题（K线图加载慢） | 中 | 中 | 每页5只，懒加载K线图数据 |
| 并发更新冲突 | 低 | 低 | MongoDB 原子更新 |

---

## 11. 附录

### 11.1 相关文件清单

**后端**:
- `backend/app/api/routes/daily_stock_signals.py` - 新增状态更新 API
- `backend/app/services/daily_stock_signals_service.py` - 修改排序逻辑，`_truncate_group_stocks` 增加 `user_state`
- `backend/app/data/mongo_daily_stock_signals.py` - 新增状态更新函数
- `backend/scripts/daily/generate_daily_stock_signals.py` - 修改以保留 user_state
- `backend/scripts/daily/backfill_stock_signals.py` - 同样需要修改以保留 user_state

**前端**:
- `frontend/pages/index.js` - 增加"详情"按钮和排序高亮
- `frontend/pages/resonance-details.js` - 新增详情页
- `frontend/styles/globals.css` - 新增样式

### 11.2 接口变更汇总

| 接口 | 变更类型 | 说明 |
|------|----------|------|
| PUT /daily-stock-signals/resonance/state | 新增 | 更新股票状态 |
| GET /daily-stock-signals/overview | 修改 | 返回 user_state，排序前置 |
| GET /daily-stock-signals/stock/{ts_code}/patterns | 修改 | 返回 user_state |

---

*文档版本: 1.0*
*最后更新: 2026-06-07*
