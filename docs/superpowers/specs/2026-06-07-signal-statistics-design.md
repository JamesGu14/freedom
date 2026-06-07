# 信号统计页面 设计文档

> 日期: 2026-06-07
> 项目: Freedom Quant Platform
> 作者: AI Assistant

---

## 1. 需求概述

在首页下方增加一个新页面"信号统计"，统计在过去不同时间窗口内频繁出现买入共振信号的股票。

### 1.1 用户故事

- 作为交易者，我想发现过去一周内多次出现买入共振信号的股票，以便快速识别热点
- 作为交易者，我想查看过去两周/一个月内持续出现共振信号的股票，以便发现趋势
- 作为交易者，我想通过日期选择查看任意交易日的统计结果

### 1.2 功能清单

| 功能 | 优先级 | 说明 |
|------|--------|------|
| 日期选择器 | P0 | 和首页类似的日期下拉框 |
| 统计面板1 | P0 | 过去7天出现≥2次买入共振 |
| 统计面板2 | P0 | 过去14天出现≥2次买入共振 |
| 统计面板3 | P0 | 过去30天出现≥3次买入共振 |
| 股票卡片 | P0 | 显示股票信息+共振次数 |
| 详情按钮 | P0 | 跳转到详情页查看K线图 |
| 个股K线 | P1 | 点击股票跳转到K线页面 |

---

## 2. 数据模型

### 2.1 数据源

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
    }
  ]
}
```

### 2.2 统计逻辑

**核心概念**：统计每只股票在过去 N 个交易日内，出现在买入共振组中的天数。

**注意**：
- 一只股票在同一天可能出现在多个共振级别（如极强+强），但只算1天
- 统计的是"出现共振的天数"，不是"共振级别数量"

**算法**：
1. 获取指定日期前 N 个交易日的日期列表
2. 查询 `daily_stock_pattern_resonance`，条件：`trade_date` 在日期列表内，`signal_side` = "buy"
3. 对每个股票，统计其在多少个不同的 `trade_date` 中出现
4. 过滤出出现次数 ≥ 阈值的股票
5. 按出现次数降序排列

---

## 3. 后端 API 设计

### 3.1 新增 API

#### GET /daily-stock-signals/statistics

获取信号统计数据。

**参数**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| trade_date | string | 否 | 结束日期，YYYYMMDD，默认为最新交易日 |

**响应**：

```json
{
  "trade_date": "20250606",
  "panels": [
    {
      "id": "7d_2",
      "title": "过去7天出现≥2次买入共振",
      "window_days": 7,
      "threshold": 2,
      "count": 5,
      "stocks": [
        {
          "ts_code": "000001.SZ",
          "name": "平安银行",
          "industry": "银行",
          "close": 12.50,
          "pct_chg": 2.35,
          "volume_ratio": 1.8,
          "resonance_count": 3,
          "latest_resonance_level": "very_strong",
          "latest_trade_date": "20250606"
        }
      ]
    },
    {
      "id": "14d_2",
      "title": "过去14天出现≥2次买入共振",
      "window_days": 14,
      "threshold": 2,
      "count": 8,
      "stocks": [...]
    },
    {
      "id": "30d_3",
      "title": "过去30天出现≥3次买入共振",
      "window_days": 30,
      "threshold": 3,
      "count": 12,
      "stocks": [...]
    }
  ]
}
```

**字段说明**：

| 字段 | 说明 |
|------|------|
| trade_date | 统计截止日期 |
| panels | 统计面板列表 |
| panels[].id | 面板标识 |
| panels[].title | 面板标题 |
| panels[].window_days | 统计窗口天数 |
| panels[].threshold | 出现次数阈值 |
| panels[].count | 符合条件的股票数量 |
| panels[].stocks | 股票列表 |
| stocks[].resonance_count | 出现共振的天数 |
| stocks[].latest_resonance_level | 最新一天的共振级别 |
| stocks[].latest_trade_date | 最新出现共振的日期 |

**实现逻辑**：

```python
def get_signal_statistics(trade_date: str | None = None) -> dict[str, Any]:
    # 1. 确定结束日期
    selected_date = trade_date or get_latest_trade_date()
    
    # 2. 定义统计配置
    configs = [
        {"id": "7d_2", "title": "过去7天出现≥2次买入共振", "window_days": 7, "threshold": 2},
        {"id": "14d_2", "title": "过去14天出现≥2次买入共振", "window_days": 14, "threshold": 2},
        {"id": "30d_3", "title": "过去30天出现≥3次买入共振", "window_days": 30, "threshold": 3},
    ]
    
    # 3. 获取交易日历
    all_trading_days = get_trading_days_before(selected_date, max_days=30)
    
    # 4. 查询所有相关数据
    all_resonance_data = query_resonance_data(all_trading_days)
    
    # 5. 计算每个面板的统计结果
    panels = []
    for config in configs:
        window_days = config["window_days"]
        threshold = config["threshold"]
        
        # 获取窗口内的交易日
        trading_days = all_trading_days[-window_days:]
        
        # 统计每只股票出现的天数
        stock_counts = count_resonance_by_stock(all_resonance_data, trading_days)
        
        # 过滤并排序
        filtered_stocks = filter_and_sort_stocks(stock_counts, threshold)
        
        panels.append({
            "id": config["id"],
            "title": config["title"],
            "window_days": window_days,
            "threshold": threshold,
            "count": len(filtered_stocks),
            "stocks": filtered_stocks,
        })
    
    return {"trade_date": selected_date, "panels": panels}
```

**MongoDB 聚合查询**：

```python
def query_resonance_data(trading_days: list[str]) -> list[dict[str, Any]]:
    """查询指定日期范围内的所有买入共振数据。"""
    collection = get_collection("daily_stock_pattern_resonance")
    
    cursor = collection.find(
        {
            "trade_date": {"$in": trading_days},
            "signal_side": "buy",
        },
        {"_id": 0, "trade_date": 1, "resonance_level": 1, "stocks.ts_code": 1, "stocks.name": 1, 
         "stocks.industry": 1, "stocks.close": 1, "stocks.pct_chg": 1, "stocks.volume_ratio": 1}
    )
    
    return list(cursor)
```

**统计函数**：

```python
def count_resonance_by_stock(resonance_data: list[dict], trading_days: list[str]) -> dict[str, dict]:
    """统计每只股票在指定日期范围内出现共振的天数。"""
    stock_map: dict[str, dict] = {}
    
    for doc in resonance_data:
        if doc["trade_date"] not in trading_days:
            continue
            
        for stock in doc.get("stocks", []):
            ts_code = stock["ts_code"]
            
            if ts_code not in stock_map:
                stock_map[ts_code] = {
                    "ts_code": ts_code,
                    "name": stock.get("name"),
                    "industry": stock.get("industry"),
                    "close": stock.get("close"),
                    "pct_chg": stock.get("pct_chg"),
                    "volume_ratio": stock.get("volume_ratio"),
                    "resonance_dates": set(),
                    "latest_trade_date": doc["trade_date"],
                    "latest_resonance_level": doc["resonance_level"],
                }
            
            stock_info = stock_map[ts_code]
            stock_info["resonance_dates"].add(doc["trade_date"])
            
            # 更新最新数据
            if doc["trade_date"] >= stock_info["latest_trade_date"]:
                stock_info["latest_trade_date"] = doc["trade_date"]
                stock_info["latest_resonance_level"] = doc["resonance_level"]
                stock_info["close"] = stock.get("close")
                stock_info["pct_chg"] = stock.get("pct_chg")
                stock_info["volume_ratio"] = stock.get("volume_ratio")
    
    return stock_map
```

**过滤和排序**：

```python
def filter_and_sort_stocks(stock_map: dict[str, dict], threshold: int) -> list[dict]:
    """过滤出出现次数≥阈值的股票，并按次数降序排列。"""
    result = []
    
    for ts_code, info in stock_map.items():
        count = len(info["resonance_dates"])
        if count >= threshold:
            result.append({
                "ts_code": info["ts_code"],
                "name": info["name"],
                "industry": info["industry"],
                "close": info["close"],
                "pct_chg": info["pct_chg"],
                "volume_ratio": info["volume_ratio"],
                "resonance_count": count,
                "latest_resonance_level": info["latest_resonance_level"],
                "latest_trade_date": info["latest_trade_date"],
            })
    
    # 按共振次数降序排列
    result.sort(key=lambda s: (-s["resonance_count"], s["ts_code"]))
    
    return result
```

---

## 4. 前端设计

### 4.1 页面路由

**文件**: `frontend/pages/signal-statistics.js`

**URL**: `/signal-statistics`

### 4.2 页面布局

```
┌─────────────────────────────────────────┐
│ Signal Statistics                       │
│                                         │
│ [日期下拉框: 2025-06-06 ▼] [查询]       │
│                                         │
│ ┌─────────────────────────────────────┐ │
│ │ 📊 过去7天出现≥2次买入共振 (5只)    │ │
│ │                                     │ │
│ │ ┌─────┐ ┌─────┐ ┌─────┐          │ │
│ │ │平安 │ │万科 │ │招商 │          │ │
│ │ │银行 │ │A   │ │银行 │          │ │
│ │ │     │ │     │ │     │          │ │
│ │ │3次  │ │2次  │ │2次  │          │ │
│ │ └─────┘ └─────┘ └─────┘          │ │
│ │                          [详情]   │ │
│ └─────────────────────────────────────┘ │
│                                         │
│ ┌─────────────────────────────────────┐ │
│ │ 📊 过去14天出现≥2次买入共振 (8只)   │ │
│ │ ...                                 │ │
│ │                          [详情]     │ │
│ └─────────────────────────────────────┘ │
│                                         │
│ ┌─────────────────────────────────────┐ │
│ │ 📊 过去30天出现≥3次买入共振 (12只)  │ │
│ │ ...                                 │ │
│ │                          [详情]     │ │
│ └─────────────────────────────────────┘ │
└─────────────────────────────────────────┘
```

### 4.3 组件结构

```jsx
export default function SignalStatisticsPage() {
  const [dates, setDates] = useState([]);
  const [selectedDate, setSelectedDate] = useState("");
  const [panels, setPanels] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // 加载日期列表
  useEffect(() => {
    const loadDates = async () => {
      try {
        const res = await apiFetch("/daily-stock-signals/dates");
        if (!res.ok) throw new Error("加载日期失败");
        const data = await res.json();
        const items = (data.items || []).map(normalizeDateValue).filter(Boolean);
        setDates(items);
        if (items.length > 0) {
          setSelectedDate(items[0]);
          loadStatistics(items[0]);
        }
      } catch (err) {
        setError(err.message || "加载日期失败");
      }
    };
    loadDates();
  }, []);

  // 加载统计数据
  const loadStatistics = async (tradeDate) => {
    setLoading(true);
    setError("");
    try {
      const res = await apiFetch(`/daily-stock-signals/statistics?trade_date=${tradeDate}`);
      if (!res.ok) throw new Error(`加载失败: ${res.status}`);
      const data = await res.json();
      setPanels(data.panels || []);
    } catch (err) {
      setError(err.message || "加载失败");
      setPanels([]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="page">
      <header className="header">
        <div>
          <p className="eyebrow">Quant Platform</p>
          <h1>信号统计</h1>
        </div>
      </header>

      <div className="toolbar">
        <select value={selectedDate} onChange={(e) => setSelectedDate(e.target.value)}>
          {dates.map((date) => (
            <option key={date} value={date}>{formatDate(date)}</option>
          ))}
        </select>
        <button onClick={() => loadStatistics(selectedDate)} disabled={loading}>
          {loading ? "加载中..." : "查询"}
        </button>
      </div>

      {error && <div className="error">{error}</div>}

      {panels.map((panel) => (
        <StatisticsPanel key={panel.id} panel={panel} />
      ))}
    </main>
  );
}
```

### 4.4 统计面板组件

```jsx
function StatisticsPanel({ panel }) {
  const [page, setPage] = useState(1);
  const pageSize = 20;

  const totalPages = Math.ceil(panel.stocks.length / pageSize);
  const pageItems = panel.stocks.slice((page - 1) * pageSize, page * pageSize);

  return (
    <section className="signal-card resonance-card">
      <div className="signal-card__header">
        <h3>{panel.title}</h3>
        <div className="signal-card__header-right">
          <span className="signal-card__count">{panel.count || 0} 只</span>
          {panel.count > 0 && (
            <Link
              href={`/resonance-details?trade_date=${panel.stocks[0]?.latest_trade_date}&signal_side=buy&resonance_level=${panel.stocks[0]?.latest_resonance_level}`}
              className="resonance-detail-btn"
            >
              详情
            </Link>
          )}
        </div>
      </div>

      <div className="signal-stock-grid">
        {pageItems.map((stock) => (
          <div key={stock.ts_code} className="signal-stock-cell">
            <div className="signal-stock-cell__head">
              <span className="signal-stock-cell__name">{stock.name || stock.ts_code}</span>
              <span className="signal-stock-cell__code">{stock.ts_code}</span>
            </div>
            <div className="signal-stock-cell__info">
              <span>{stock.industry || "-"}</span>
              <span>收盘 {formatNumber(stock.close)}</span>
              <span className={Number(stock.pct_chg) > 0 ? "text-red" : "text-green"}>
                {formatPct(stock.pct_chg)}
              </span>
              <span>量比 {formatNumber(stock.volume_ratio)}</span>
            </div>
            <div className="signal-stock-cell__tags">
              <span className="signal-tag">{stock.resonance_count} 次共振</span>
              <span className="signal-tag">{getResonanceLabel(stock.latest_resonance_level)}</span>
            </div>
            <div className="signal-stock-cell__foot">
              <span>最新: {formatDate(stock.latest_trade_date)}</span>
              <Link className="link-button" href={`/stocks/${stock.ts_code}`}>K线</Link>
            </div>
          </div>
        ))}
      </div>

      {totalPages > 1 && (
        <div className="pagination">
          <button disabled={page <= 1} onClick={() => setPage(p => p - 1)}>‹ 上一页</button>
          <span>{page} / {totalPages} 页</span>
          <button disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>下一页 ›</button>
        </div>
      )}
    </section>
  );
}
```

### 4.5 导航集成

在 `_app.js` 的导航菜单中增加"信号统计"入口：

```jsx
const NAV = [
  { label: "首页", href: "/" },
  { label: "信号", href: "/daily-signals" },
  { label: "信号统计", href: "/signal-statistics" },
  // ... 其他导航项
];
```

---

## 5. 样式设计

复用现有的 `.signal-card`、`.signal-stock-grid`、`.signal-stock-cell` 等样式，不需要新增大量 CSS。

**新增样式**（如果需要）：

```css
.signal-stock-cell__tags {
  display: flex;
  gap: 4px;
  margin-top: 8px;
  flex-wrap: wrap;
}

.signal-tag {
  padding: 2px 8px;
  border-radius: 4px;
  background: var(--accent-subtle);
  color: var(--accent-dark);
  font-size: 12px;
}
```

---

## 6. 性能考虑

### 6.1 查询优化

- 使用 `trade_date` + `signal_side` 的复合索引（已存在）
- 限制查询字段，不返回 `patterns` 等大数据字段
- 一次查询获取所有需要的数据，避免多次数据库往返

### 6.2 缓存策略

```python
cache_key = f"signals:statistics:{trade_date}"
cached = cache_get(cache_key)
if cached is not None:
    return cached

# ... 计算统计结果 ...

cache_set(cache_key, result, ttl_seconds=86400)  # 缓存1天
```

---

## 7. 测试计划

### 7.1 单元测试

1. **统计计算测试**
   - 测试过去7天统计
   - 测试过去14天统计
   - 测试过去30天统计
   - 测试阈值过滤

2. **日期计算测试**
   - 测试交易日获取
   - 测试边界情况（节假日、周末）

### 7.2 集成测试

1. 选择日期后，三个面板正确显示
2. 股票卡片显示共振次数
3. 点击"详情"跳转到共振详情页
4. 点击"K线"跳转到股票K线页

---

## 8. 风险评估

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|----------|
| 数据量大时查询慢 | 中 | 中 | 限制返回字段，使用缓存 |
| 日期计算错误 | 低 | 高 | 使用交易日历，充分测试 |
| 面板为空 | 中 | 低 | 显示空状态提示 |

---

## 9. 附录

### 9.1 相关文件清单

**后端**:
- `backend/app/api/routes/daily_stock_signals.py` - 新增 statistics API
- `backend/app/services/daily_stock_signals_service.py` - 新增统计服务函数
- `backend/app/data/mongo_daily_stock_signals.py` - 新增查询函数（如需要）

**前端**:
- `frontend/pages/signal-statistics.js` - 新增统计页面
- `frontend/pages/_app.js` - 增加导航入口

### 9.2 接口变更汇总

| 接口 | 变更类型 | 说明 |
|------|----------|------|
| GET /daily-stock-signals/statistics | 新增 | 获取信号统计数据 |

---

*文档版本: 1.0*
*最后更新: 2026-06-07*
