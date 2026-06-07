# 极强共振详情页 + 状态管理 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在首页极强共振面板增加"详情"按钮，跳转到新页面展示股票K线图列表，支持忽略/认可状态管理，并在首页高亮排序认可的股票。

**Architecture:** 扩展现有 `daily_stock_pattern_resonance` 集合的 `stocks[]` 数组，增加 `user_state` 字段。后端新增 PUT API 更新状态，修改 overview API 排序。前端新增 `/resonance-details` 页面，复用 ECharts 渲染K线图，MA数据客户端计算。

**Tech Stack:** Next.js 14 + FastAPI + MongoDB + ECharts + Redis (cache)

---

## 文件结构

### 后端文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/app/api/routes/daily_stock_signals.py` | 修改 | 新增 PUT `/resonance/state` 接口 |
| `backend/app/services/daily_stock_signals_service.py` | 修改 | `_truncate_group_stocks` 增加 `user_state`，排序逻辑 |
| `backend/app/data/mongo_daily_stock_signals.py` | 修改 | 新增 `update_stock_resonance_state` 函数 |
| `backend/scripts/daily/generate_daily_stock_signals.py` | 修改 | 信号重算时保留 `user_state` |
| `backend/scripts/daily/backfill_stock_signals.py` | 修改 | 信号回填时保留 `user_state` |

### 前端文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `frontend/pages/index.js` | 修改 | ResonanceCard 增加"详情"按钮，StockList 排序高亮 |
| `frontend/pages/resonance-details.js` | 创建 | 极强详情页 |
| `frontend/styles/globals.css` | 修改 | 新增样式 |

---

## Task 1: 后端 - 新增状态更新数据层函数

**Files:**
- Modify: `backend/app/data/mongo_daily_stock_signals.py`

- [ ] **Step 1: 在 mongo_daily_stock_signals.py 底部新增状态更新函数**

在文件末尾（`list_signals_for_stock` 函数之后）添加：

```python
def update_stock_resonance_state(
    trade_date: str,
    ts_code: str,
    signal_side: str,
    resonance_level: str,
    user_state: str | None,
) -> bool:
    """更新股票在共振数据中的 user_state。
    
    Returns:
        True if stock was found and updated, False otherwise.
    """
    ensure_daily_stock_signal_indexes()
    
    result = get_collection("daily_stock_pattern_resonance").update_one(
        {
            "trade_date": trade_date,
            "signal_side": signal_side,
            "resonance_level": resonance_level,
            "stocks.ts_code": ts_code,
        },
        {"$set": {"stocks.$.user_state": user_state}},
    )
    
    return result.matched_count > 0
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/data/mongo_daily_stock_signals.py
git commit -m "feat: add update_stock_resonance_state function"
```

---

## Task 2: 后端 - 新增状态更新 API 接口

**Files:**
- Modify: `backend/app/api/routes/daily_stock_signals.py`

- [ ] **Step 1: 在文件顶部添加必要的导入**

```python
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.daily_stock_signals_service import (
    get_daily_stock_signal_by_type,
    get_daily_stock_signals_overview,
    get_stock_pattern_details,
    get_stock_recent_signals,
    list_available_daily_stock_signal_dates,
)
from app.data.mongo_daily_stock_signals import update_stock_resonance_state
from app.core.cache import cache_delete_pattern
```

- [ ] **Step 2: 在 router 定义后添加 Pydantic 模型**

```python
class ResonanceStatePayload(BaseModel):
    trade_date: str = Field(..., min_length=8, max_length=8)
    ts_code: str = Field(..., min_length=1, max_length=32)
    signal_side: str = Field(..., pattern="^(buy|sell)$")
    resonance_level: str = Field(..., pattern="^(very_strong|strong|normal)$")
    user_state: str | None = Field(default=None)
    
    @field_validator("user_state")
    @classmethod
    def validate_user_state(cls, v: str | None) -> str | None:
        if v is not None and v not in ("acknowledged", "ignored"):
            raise ValueError('user_state must be "acknowledged", "ignored", or null')
        return v
```

- [ ] **Step 3: 在文件底部添加 PUT 接口**

```python
@router.put("/daily-stock-signals/resonance/state")
def update_resonance_state(payload: ResonanceStatePayload) -> dict[str, object]:
    success = update_stock_resonance_state(
        trade_date=payload.trade_date,
        ts_code=payload.ts_code,
        signal_side=payload.signal_side,
        resonance_level=payload.resonance_level,
        user_state=payload.user_state,
    )
    
    if not success:
        raise HTTPException(status_code=404, detail="Stock not found in resonance group")
    
    # 清除相关缓存
    cache_delete_pattern(f"signals:overview:{payload.trade_date}:*")
    cache_delete_pattern(f"signals:patterns:*:{payload.trade_date}")
    
    return {
        "success": True,
        "trade_date": payload.trade_date,
        "ts_code": payload.ts_code,
        "user_state": payload.user_state,
    }
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/routes/daily_stock_signals.py
git commit -m "feat: add PUT /daily-stock-signals/resonance/state API"
```

---

## Task 3: 后端 - 修改 overview API 返回 user_state 并排序

**Files:**
- Modify: `backend/app/services/daily_stock_signals_service.py`

- [ ] **Step 1: 修改 `_truncate_group_stocks` 函数**

找到 `_truncate_group_stocks` 函数（约第29-45行），在 `stocks` 列表推导中添加 `user_state`：

```python
def _truncate_group_stocks(group: dict[str, Any], top_n: int) -> dict[str, Any]:
    doc = dict(group)
    stocks = (doc.get("stocks") or [])[:top_n]
    doc["stocks"] = [
        {
            "ts_code": s.get("ts_code"),
            "name": s.get("name"),
            "industry": s.get("industry"),
            "close": s.get("close"),
            "pct_chg": s.get("pct_chg"),
            "volume_ratio": s.get("volume_ratio"),
            "weighted_score": s.get("weighted_score"),
            "patterns": _truncate_patterns(s.get("patterns")),
            "user_state": s.get("user_state"),  # 新增
        }
        for s in stocks
    ]
    return doc
```

- [ ] **Step 2: 在 `get_daily_stock_signals_overview` 函数中添加排序逻辑**

找到 `get_daily_stock_signals_overview` 函数（约第48-88行），在返回结果前添加排序：

```python
def _sort_stocks_by_state(stocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """认可的股票排在最前面，其余保持原有顺序。"""
    return sorted(
        stocks,
        key=lambda s: (0 if s.get("user_state") == "acknowledged" else 1, -s.get("weighted_score", 0))
    )
```

然后在 `result = {` 之前添加：

```python
    # 对共振组中的股票按状态排序
    for group in result["buy_resonance"]:
        group["stocks"] = _sort_stocks_by_state(group.get("stocks", []))
    for group in result["sell_resonance"]:
        group["stocks"] = _sort_stocks_by_state(group.get("stocks", []))
```

- [ ] **Step 3: 修改 `get_stock_pattern_details` 函数返回 user_state**

找到 `get_stock_pattern_details` 函数（约第141-176行），在 `result = {` 中添加 `user_state`：

```python
                result = {
                    "ts_code": ts_code,
                    "trade_date": trade_date,
                    "name": stock.get("name"),
                    "industry": stock.get("industry"),
                    "close": stock.get("close"),
                    "pct_chg": stock.get("pct_chg"),
                    "volume_ratio": stock.get("volume_ratio"),
                    "weighted_score": stock.get("weighted_score"),
                    "resonance_level": doc.get("resonance_level"),
                    "signal_side": doc.get("signal_side"),
                    "user_state": stock.get("user_state"),  # 新增
                    "patterns": [
                        {
                            "pattern": p,
                            "weight": get_pattern_weight(p),
                            "category": get_pattern_category_label(p),
                        }
                        for p in patterns
                    ],
                }
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/daily_stock_signals_service.py
git commit -m "feat: return user_state in overview and pattern details, sort acknowledged first"
```

---

## Task 4: 后端 - 信号重算脚本保留 user_state

**Files:**
- Modify: `backend/scripts/daily/generate_daily_stock_signals.py`
- Modify: `backend/scripts/daily/backfill_stock_signals.py`

- [ ] **Step 1: 在 mongo_daily_stock_signals.py 中新增 preserve_user_states 函数**

在 `update_stock_resonance_state` 函数之后添加：

```python
def preserve_user_states(
    trade_date: str,
    signal_side: str,
    resonance_level: str,
    new_stocks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """保留现有 user_state 并在新数据中合并。
    
    在信号重算前调用，将旧数据中的 user_state 合并到新数据。
    """
    collection = get_collection("daily_stock_pattern_resonance")
    
    existing = collection.find_one(
        {
            "trade_date": trade_date,
            "signal_side": signal_side,
            "resonance_level": resonance_level,
        },
        {"stocks.ts_code": 1, "stocks.user_state": 1}
    )
    
    if not existing:
        return new_stocks
    
    state_map = {
        s["ts_code"]: s.get("user_state")
        for s in existing.get("stocks", [])
        if s.get("user_state") is not None
    }
    
    for stock in new_stocks:
        ts_code = stock.get("ts_code")
        if ts_code in state_map:
            stock["user_state"] = state_map[ts_code]
    
    return new_stocks
```

- [ ] **Step 2: 在 generate_daily_stock_signals.py 中调用 preserve_user_states**

找到调用 `upsert_daily_stock_pattern_resonance` 的地方，在其之前添加：

```python
from app.data.mongo_daily_stock_signals import preserve_user_states

# ... 在 upsert 之前 ...
stocks = preserve_user_states(trade_date, signal_side, resonance_level, stocks)
```

- [ ] **Step 3: 在 backfill_stock_signals.py 中同样调用 preserve_user_states**

找到调用 `upsert_daily_stock_pattern_resonance` 的地方，同样添加：

```python
from app.data.mongo_daily_stock_signals import preserve_user_states

# ... 在 upsert 之前 ...
stocks = preserve_user_states(trade_date, signal_side, resonance_level, stocks)
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/data/mongo_daily_stock_signals.py
git add backend/scripts/daily/generate_daily_stock_signals.py
git add backend/scripts/daily/backfill_stock_signals.py
git commit -m "feat: preserve user_state during signal recalculation"
```

---

## Task 5: 前端 - 修改首页增加详情按钮和排序高亮

**Files:**
- Modify: `frontend/pages/index.js`
- Modify: `frontend/styles/globals.css`

- [ ] **Step 1: 修改 ResonanceCard 组件**

找到 `ResonanceCard` 组件（约第489-497行），修改为：

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

- [ ] **Step 2: 修改 StockList 组件排序和高亮**

找到 `StockList` 组件（约第407-478行），在 `useEffect` 后添加排序逻辑：

```jsx
const StockList = ({ stocks = [], tradeDate = "" }) => {
  const [page, setPage] = useState(1);
  const [popupStock, setPopupStock] = useState(null);
  const [patternStock, setPatternStock] = useState(null);

  useEffect(() => { setPage(1); }, [stocks]);

  // 排序：认可的排在最前面
  const sortedStocks = useMemo(() => {
    return [...stocks].sort((a, b) => {
      const aAck = a.user_state === "acknowledged" ? 1 : 0;
      const bAck = b.user_state === "acknowledged" ? 1 : 0;
      if (aAck !== bAck) return bAck - aAck;
      return 0;
    });
  }, [stocks]);

  if (!stocks.length) {
    return <div className="signal-empty">当日无命中</div>;
  }

  const totalPages = Math.ceil(sortedStocks.length / PAGE_SIZE);
  const pageItems = sortedStocks.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
```

然后修改 `signal-stock-cell` 的 className：

```jsx
          <div 
            key={`${item.ts_code}-${item.signal_count || item.signal_count_same_side || item.weighted_score || 0}`} 
            className={`signal-stock-cell ${item.user_state === "acknowledged" ? "signal-stock-cell--acknowledged" : ""}`}
          >
```

- [ ] **Step 3: 在 globals.css 中添加高亮样式**

在文件末尾添加：

```css
.signal-stock-cell--acknowledged {
  border: 2px solid #f59e0b;
  background-color: rgba(245, 158, 11, 0.05);
  box-shadow: 0 0 8px rgba(245, 158, 11, 0.2);
}

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

- [ ] **Step 4: Commit**

```bash
git add frontend/pages/index.js
git add frontend/styles/globals.css
git commit -m "feat: add detail button and acknowledged highlight on homepage"
```

---

## Task 6: 前端 - 创建极强详情页

**Files:**
- Create: `frontend/pages/resonance-details.js`

- [ ] **Step 1: 创建 resonance-details.js 文件**

```jsx
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/router";
import Link from "next/link";
import { apiFetch } from "../lib/api";

const formatDate = (value) => {
  if (!value) return "";
  const s = String(value).trim();
  if (s.length !== 8) return s;
  return `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}`;
};

const RESONANCE_LABELS = {
  very_strong: "极强共振 (14+)",
  strong: "强共振 (9+)",
  normal: "普通共振 (5+)",
};

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

function StockDetailCard({ stock, tradeDate, signalSide, resonanceLevel, onUpdateState }) {
  const [candles, setCandles] = useState([]);
  const [chartLoading, setChartLoading] = useState(true);
  const [chartError, setChartError] = useState("");

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

  const isAcknowledged = stock.user_state === "acknowledged";
  const isIgnored = stock.user_state === "ignored";

  return (
    <div className={`stock-detail-card ${isAcknowledged ? "acknowledged" : ""}`}>
      <div className="stock-detail-header">
        <h3>{stock.name} ({stock.ts_code})</h3>
        <span>{stock.industry || "-"}</span>
        <span>收盘 {stock.close || "-"}</span>
        <span className={Number(stock.pct_chg) > 0 ? "text-red" : "text-green"}>
          {stock.pct_chg ? `${Number(stock.pct_chg).toFixed(2)}%` : "-"}
        </span>
      </div>

      {chartLoading && <div className="chart-loading">加载 K 线数据中...</div>}
      {chartError && <div className="chart-error">{chartError}</div>}
      
      {!chartLoading && !chartError && candles.length > 0 && (
        <CandlestickChart candles={candles} />
      )}

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

function CandlestickChart({ candles }) {
  const chartRef = useRef(null);
  const chartInstanceRef = useRef(null);

  useEffect(() => {
    if (!chartRef.current || !candles.length) return;

    if (chartInstanceRef.current) {
      chartInstanceRef.current.dispose();
    }

    const chart = echarts.init(chartRef.current);
    chartInstanceRef.current = chart;

    const dates = candles.map(c => c.trade_date);
    const candleData = candles.map(c => [c.open, c.close, c.low, c.high]);
    const closes = candles.map(c => c.close);
    const ma5 = calculateMA(closes, 5);
    const ma10 = calculateMA(closes, 10);
    const ma20 = calculateMA(closes, 20);

    const option = {
      grid: { left: 50, right: 20, top: 20, bottom: 30 },
      xAxis: { type: "category", data: dates, axisLabel: { fontSize: 10 } },
      yAxis: { type: "value", scale: true, axisLabel: { fontSize: 10 } },
      series: [
        {
          type: "candlestick",
          data: candleData,
          itemStyle: {
            color: "#ea3943",
            color0: "#00a650",
            borderColor: "#ea3943",
            borderColor0: "#00a650",
          },
        },
        { name: "MA5", type: "line", data: ma5, smooth: true, lineStyle: { width: 1 }, symbol: "none" },
        { name: "MA10", type: "line", data: ma10, smooth: true, lineStyle: { width: 1 }, symbol: "none" },
        { name: "MA20", type: "line", data: ma20, smooth: true, lineStyle: { width: 1 }, symbol: "none" },
      ],
      tooltip: { trigger: "axis" },
      legend: { data: ["MA5", "MA10", "MA20"], top: 0, textStyle: { fontSize: 10 } },
    };

    chart.setOption(option);

    return () => {
      chart.dispose();
      chartInstanceRef.current = null;
    };
  }, [candles]);

  return <div ref={chartRef} className="stock-detail-chart" style={{ height: 300 }} />;
}

export default function ResonanceDetailsPage() {
  const router = useRouter();
  const { trade_date, signal_side, resonance_level } = router.query;

  const [stocks, setStocks] = useState([]);
  const [filter, setFilter] = useState("all");
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const pageSize = 5;

  // 加载共振数据
  useEffect(() => {
    if (!trade_date || !signal_side || !resonance_level) return;

    let cancelled = false;
    setLoading(true);
    setError("");

    apiFetch(`/daily-stock-signals/overview?trade_date=${trade_date}`)
      .then(async (res) => {
        if (!res.ok) throw new Error("加载失败");
        const data = await res.json();
        if (cancelled) return;

        const resonanceGroups = signal_side === "buy" ? data.buy_resonance : data.sell_resonance;
        const group = resonanceGroups.find(g => g.resonance_level === resonance_level);

        if (group) {
          setStocks(group.stocks || []);
        } else {
          setStocks([]);
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err.message || "加载失败");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => { cancelled = true; };
  }, [trade_date, signal_side, resonance_level]);

  // 筛选切换时重置到第一页
  useEffect(() => {
    setPage(1);
  }, [filter]);

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

  const totalPages = Math.max(Math.ceil(filteredStocks.length / pageSize), 1);
  const pageItems = filteredStocks.slice((page - 1) * pageSize, page * pageSize);

  // 状态更新（带错误回滚）
  const updateStockState = async (tsCode, newState) => {
    const previousState = stocks.find(s => s.ts_code === tsCode)?.user_state;

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
      setStocks(prev => prev.map(s =>
        s.ts_code === tsCode ? { ...s, user_state: previousState } : s
      ));
      alert(err.message || "更新失败，请重试");
    }
  };

  if (!trade_date || !signal_side || !resonance_level) {
    return (
      <main className="page">
        <div className="error">参数错误：缺少必要的 URL 参数</div>
        <Link href="/" className="link-button">返回首页</Link>
      </main>
    );
  }

  return (
    <main className="page">
      <header className="header">
        <div>
          <p className="eyebrow">Quant Platform</p>
          <h1>极强共振详情</h1>
          <p className="subtitle">
            {formatDate(trade_date)} · {signal_side === "buy" ? "买入" : "卖出"} · {RESONANCE_LABELS[resonance_level] || resonance_level}
          </p>
        </div>
        <Link href="/" className="link-button">返回首页</Link>
      </header>

      {error && <div className="error">{error}</div>}

      {loading ? (
        <div className="loading-container">
          <div className="spinner"></div>
          <p>加载中...</p>
        </div>
      ) : (
        <>
          {/* 筛选器 */}
          <div className="filter-tabs">
            <button className={filter === "all" ? "filter-tab active" : "filter-tab"} onClick={() => setFilter("all")}>
              全部 ({stocks.length})
            </button>
            <button className={filter === "acknowledged" ? "filter-tab active" : "filter-tab"} onClick={() => setFilter("acknowledged")}>
              只看认可 ({stocks.filter(s => s.user_state === "acknowledged").length})
            </button>
            <button className={filter === "active" ? "filter-tab active" : "filter-tab"} onClick={() => setFilter("active")}>
              认可+未标记 ({stocks.filter(s => s.user_state !== "ignored").length})
            </button>
          </div>

          {/* 股票列表 */}
          <div className="resonance-detail-list">
            {pageItems.length === 0 ? (
              <div className="empty-state">
                <p>暂无符合条件的股票</p>
              </div>
            ) : (
              pageItems.map(stock => (
                <StockDetailCard
                  key={stock.ts_code}
                  stock={stock}
                  tradeDate={trade_date}
                  signalSide={signal_side}
                  resonanceLevel={resonance_level}
                  onUpdateState={updateStockState}
                />
              ))
            )}
          </div>

          {/* 分页 */}
          {totalPages > 1 && (
            <div className="pagination">
              <button
                type="button"
                className="pagination__btn"
                disabled={page <= 1}
                onClick={() => setPage(p => Math.max(1, p - 1))}
              >
                ‹ 上一页
              </button>
              <span className="pagination__info">
                {page} / {totalPages} 页（共 {filteredStocks.length} 只）
              </span>
              <button
                type="button"
                className="pagination__btn"
                disabled={page >= totalPages}
                onClick={() => setPage(p => Math.min(totalPages, p + 1))}
              >
                下一页 ›
              </button>
            </div>
          )}
        </>
      )}
    </main>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/pages/resonance-details.js
git commit -m "feat: add resonance details page with K-line charts"
```

---

## Task 7: 前端 - 添加详情页样式

**Files:**
- Modify: `frontend/styles/globals.css`

- [ ] **Step 1: 在 globals.css 中添加详情页样式**

在文件末尾添加：

```css
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
  flex-wrap: wrap;
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

.chart-loading,
.chart-error {
  padding: 40px;
  text-align: center;
  color: var(--muted);
  background: var(--card-bg);
  border-radius: 4px;
  margin-bottom: 12px;
}

.chart-error {
  color: var(--error);
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
  transition: background 0.2s;
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
  flex-wrap: wrap;
}

.filter-tab {
  padding: 8px 16px;
  border-radius: 4px;
  border: 1px solid var(--border);
  background: var(--btn-bg);
  cursor: pointer;
  font-size: 14px;
  transition: all 0.2s;
}

.filter-tab.active {
  background: var(--accent);
  color: white;
  border-color: var(--accent);
}

/* 详情页列表 */
.resonance-detail-list {
  margin-top: 16px;
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/styles/globals.css
git commit -m "style: add resonance details page styles"
```

---

## Task 8: 集成测试

- [ ] **Step 1: 启动后端服务**

```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 9000
```

- [ ] **Step 2: 启动前端服务**

```bash
cd frontend
npm run dev
```

- [ ] **Step 3: 测试首页**

1. 打开 http://localhost:3000/freedom/
2. 确认极强共振卡片右上角有"详情"按钮
3. 点击"详情"按钮，确认跳转到 `/resonance-details`
4. 确认认可的股票在首页有金色边框

- [ ] **Step 4: 测试详情页**

1. 在详情页确认股票列表加载正常
2. 确认每只股票显示 K 线图
3. 点击"认可"按钮，确认股票卡片有金色边框
4. 点击"忽略"按钮，确认切换到"认可+未标记"筛选后该股票消失
5. 点击"取消忽略"，确认股票重新出现

- [ ] **Step 5: 测试状态持久化**

1. 在详情页标记几只股票为"认可"
2. 刷新页面，确认状态仍然保留
3. 回到首页，确认认可的股票排在最前面

- [ ] **Step 6: Commit**

```bash
git commit -m "test: verify resonance details feature"
```

---

## 自检清单

- [x] Spec coverage: 所有需求都有对应的任务
- [x] Placeholder scan: 无 TBD/TODO
- [x] Type consistency: user_state 类型一致（str | None）
- [x] API paths: 与 routers.py 中的注册一致
- [x] Cache invalidation: 使用 cache_delete_pattern
- [x] Error handling: 乐观更新带错误回滚
- [x] Signal recalculation: 两个脚本都修改

---

**Plan complete and saved to `docs/superpowers/plans/2026-06-07-resonance-details.md`.**

**Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
