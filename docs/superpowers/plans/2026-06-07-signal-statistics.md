# 信号统计页面 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在首页下方增加一个新页面"信号统计"，统计在过去不同时间窗口内频繁出现买入共振信号的股票。

**Architecture:** 后端新增 GET /daily-stock-signals/statistics API，使用 MongoDB 聚合查询统计每只股票在过去 7/14/30 天内出现买入共振的天数。前端创建 /signal-statistics 页面，复用首页面板样式展示统计结果。

**Tech Stack:** Next.js 14 + FastAPI + MongoDB + Redis (cache)

---

## 文件结构

### 后端文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/app/api/routes/daily_stock_signals.py` | 修改 | 新增 GET `/statistics` 接口 |
| `backend/app/services/daily_stock_signals_service.py` | 修改 | 新增 `get_signal_statistics` 服务函数 |
| `backend/app/data/mongo_trade_calendar.py` | 读取 | 复用 `get_open_trading_days` 函数 |

### 前端文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `frontend/pages/signal-statistics.js` | 创建 | 信号统计页面 |
| `frontend/pages/_app.js` | 修改 | 增加导航入口 |

---

## Task 1: 后端 - 新增信号统计服务函数

**Files:**
- Modify: `backend/app/services/daily_stock_signals_service.py`

- [ ] **Step 1: 在文件顶部添加必要的导入**

```python
from app.data.mongo_trade_calendar import get_open_trading_days
```

- [ ] **Step 2: 在 `get_stock_pattern_details` 函数之后添加统计服务函数**

```python
from __future__ import annotations

import datetime as dt
from typing import Any

from app.core.cache import cache_get, cache_set
from app.data.duckdb_store import list_daily
from app.data.mongo import get_collection
from app.data.mongo_daily_stock_signals import (
    get_signal_group,
    list_daily_stock_signal_dates,
    list_resonance_groups_for_date,
    list_signal_groups_for_date,
    list_signals_for_stock,
)
from app.data.mongo_trade_calendar import get_open_trading_days
from app.signals.patterns.config import get_pattern_category_label, get_pattern_weight

# ... existing code ...

def get_signal_statistics(*, trade_date: str | None = None) -> dict[str, Any]:
    """获取信号统计数据。
    
    统计每只股票在过去 7/14/30 天内出现买入共振的天数。
    """
    # 1. 确定结束日期
    selected_date = trade_date or next(iter(list_daily_stock_signal_dates(limit=1)), None)
    if not selected_date:
        return {"trade_date": None, "panels": []}
    
    cache_key = f"signals:statistics:{selected_date}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached
    
    # 2. 定义统计配置
    configs = [
        {"id": "7d_2", "title": "过去7天出现≥2次买入共振", "window_days": 7, "threshold": 2},
        {"id": "14d_2", "title": "过去14天出现≥2次买入共振", "window_days": 14, "threshold": 2},
        {"id": "30d_3", "title": "过去30天出现≥3次买入共振", "window_days": 30, "threshold": 3},
    ]
    
    # 3. 获取交易日历（最多30天）
    end_dt = dt.datetime.strptime(selected_date, "%Y%m%d")
    start_dt = end_dt - dt.timedelta(days=45)  # 预留足够天数
    start_date = start_dt.strftime("%Y%m%d")
    
    all_trading_days = get_open_trading_days(start_date, selected_date)
    if not all_trading_days:
        return {"trade_date": selected_date, "panels": []}
    
    # 4. 查询所有相关数据
    collection = get_collection("daily_stock_pattern_resonance")
    cursor = collection.find(
        {
            "trade_date": {"$in": all_trading_days},
            "signal_side": "buy",
        },
        {
            "_id": 0,
            "trade_date": 1,
            "resonance_level": 1,
            "stocks.ts_code": 1,
            "stocks.name": 1,
            "stocks.industry": 1,
            "stocks.close": 1,
            "stocks.pct_chg": 1,
            "stocks.volume_ratio": 1,
        }
    )
    
    # 5. 构建股票数据映射
    stock_data: dict[str, dict[str, Any]] = {}
    for doc in cursor:
        trade_date = doc["trade_date"]
        resonance_level = doc.get("resonance_level", "")
        
        for stock in doc.get("stocks", []):
            ts_code = stock["ts_code"]
            
            if ts_code not in stock_data:
                stock_data[ts_code] = {
                    "ts_code": ts_code,
                    "name": stock.get("name"),
                    "industry": stock.get("industry"),
                    "close": stock.get("close"),
                    "pct_chg": stock.get("pct_chg"),
                    "volume_ratio": stock.get("volume_ratio"),
                    "resonance_dates": set(),
                    "latest_trade_date": trade_date,
                    "latest_resonance_level": resonance_level,
                }
            
            info = stock_data[ts_code]
            info["resonance_dates"].add(trade_date)
            
            # 更新最新数据
            if trade_date >= info["latest_trade_date"]:
                info["latest_trade_date"] = trade_date
                info["latest_resonance_level"] = resonance_level
                info["close"] = stock.get("close")
                info["pct_chg"] = stock.get("pct_chg")
                info["volume_ratio"] = stock.get("volume_ratio")
    
    # 6. 计算每个面板的统计结果
    panels = []
    for config in configs:
        window_days = config["window_days"]
        threshold = config["threshold"]
        
        # 获取窗口内的交易日
        window_trading_days = all_trading_days[-window_days:] if len(all_trading_days) >= window_days else all_trading_days
        window_set = set(window_trading_days)
        
        # 过滤并统计
        filtered_stocks = []
        for ts_code, info in stock_data.items():
            # 只计算窗口内的共振天数
            count_in_window = len(info["resonance_dates"] & window_set)
            
            if count_in_window >= threshold:
                filtered_stocks.append({
                    "ts_code": info["ts_code"],
                    "name": info["name"],
                    "industry": info["industry"],
                    "close": info["close"],
                    "pct_chg": info["pct_chg"],
                    "volume_ratio": info["volume_ratio"],
                    "resonance_count": count_in_window,
                    "latest_resonance_level": info["latest_resonance_level"],
                    "latest_trade_date": info["latest_trade_date"],
                })
        
        # 按共振次数降序排列
        filtered_stocks.sort(key=lambda s: (-s["resonance_count"], s["ts_code"]))
        
        panels.append({
            "id": config["id"],
            "title": config["title"],
            "window_days": window_days,
            "threshold": threshold,
            "count": len(filtered_stocks),
            "stocks": filtered_stocks,
        })
    
    result = {"trade_date": selected_date, "panels": panels}
    cache_set(cache_key, result, ttl_seconds=86400)
    return result
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/daily_stock_signals_service.py
git commit -m "feat: add signal statistics service function"
```

---

## Task 2: 后端 - 新增信号统计 API 接口

**Files:**
- Modify: `backend/app/api/routes/daily_stock_signals.py`

- [ ] **Step 1: 在文件底部添加 GET 接口**

```python
@router.get("/daily-stock-signals/statistics")
def get_signal_statistics_route(
    trade_date: str | None = Query(default=None),
) -> dict[str, Any]:
    from app.services.daily_stock_signals_service import get_signal_statistics
    return get_signal_statistics(trade_date=trade_date)
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/api/routes/daily_stock_signals.py
git commit -m "feat: add GET /daily-stock-signals/statistics API"
```

---

## Task 3: 前端 - 创建信号统计页面

**Files:**
- Create: `frontend/pages/signal-statistics.js`

- [ ] **Step 1: 创建 signal-statistics.js 文件**

```jsx
import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { apiFetch } from "../lib/api";

const normalizeDateValue = (value) => {
  if (!value) return "";
  const cleaned = String(value).replace(/-/g, "");
  return cleaned.length === 8 ? cleaned : "";
};

const formatDate = (value) => {
  const normalized = normalizeDateValue(value);
  if (!normalized) return value || "-";
  return `${normalized.slice(0, 4)}-${normalized.slice(4, 6)}-${normalized.slice(6, 8)}`;
};

const formatNumber = (value, digits = 2) => {
  if (value === null || value === undefined || value === "") return "-";
  const num = Number(value);
  if (Number.isNaN(num)) return String(value);
  return num.toLocaleString("zh-CN", { maximumFractionDigits: digits });
};

const formatPct = (value) => {
  if (value === null || value === undefined || value === "") return "-";
  const num = Number(value);
  if (Number.isNaN(num)) return String(value);
  const prefix = num > 0 ? "+" : "";
  return `${prefix}${num.toFixed(2)}%`;
};

const RESONANCE_LABELS = {
  very_strong: "极强共振",
  strong: "强共振",
  normal: "普通共振",
};

const getResonanceLabel = (l) => RESONANCE_LABELS[l] || l;

const PAGE_SIZE = 20;

/* ─── Stock List ─── */

const StockList = ({ stocks = [] }) => {
  const [page, setPage] = useState(1);

  useEffect(() => { setPage(1); }, [stocks]);

  if (!stocks.length) {
    return <div className="signal-empty">暂无符合条件的股票</div>;
  }

  const totalPages = Math.ceil(stocks.length / PAGE_SIZE);
  const pageItems = stocks.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  return (
    <div>
      <div className="signal-stock-grid">
        {pageItems.map((item) => (
          <div key={item.ts_code} className="signal-stock-cell">
            <div className="signal-stock-cell__head">
              <span className="signal-stock-cell__name">{item.name || item.ts_code}</span>
              <span className="signal-stock-cell__code">{item.ts_code}</span>
            </div>
            <div className="signal-stock-cell__info">
              <span>{item.industry || "-"}</span>
              <span>收盘 {formatNumber(item.close)}</span>
              <span className={Number(item.pct_chg) > 0 ? "text-red" : Number(item.pct_chg) < 0 ? "text-green" : ""}>
                {formatPct(item.pct_chg)}
              </span>
              <span>量比 {formatNumber(item.volume_ratio)}</span>
            </div>
            <div className="signal-stock-cell__tags">
              <span className="signal-tag">{item.resonance_count} 次共振</span>
              <span className="signal-tag">{getResonanceLabel(item.latest_resonance_level)}</span>
            </div>
            <div className="signal-stock-cell__foot">
              <span>最新: {formatDate(item.latest_trade_date)}</span>
              <div className="signal-stock-cell__actions">
                <Link className="link-button" href={`/stocks/${item.ts_code}`}>K线</Link>
              </div>
            </div>
          </div>
        ))}
      </div>
      {totalPages > 1 && (
        <div className="pagination">
          <button type="button" className="pagination__btn" disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>‹ 上一页</button>
          <span className="pagination__info">{page} / {totalPages} 页（共 {stocks.length} 只）</span>
          <button type="button" className="pagination__btn" disabled={page >= totalPages} onClick={() => setPage((p) => Math.min(totalPages, p + 1))}>下一页 ›</button>
        </div>
      )}
    </div>
  );
};

/* ─── Statistics Panel ─── */

const StatisticsPanel = ({ panel }) => (
  <section className="signal-card resonance-card">
    <div className="signal-card__header">
      <h3>{panel.title}</h3>
      <div className="signal-card__header-right">
        <span className="signal-card__count">{panel.count || 0} 只</span>
        {panel.count > 0 && panel.stocks[0]?.latest_trade_date && (
          <Link
            href={`/resonance-details?trade_date=${panel.stocks[0].latest_trade_date}&signal_side=buy&resonance_level=${panel.stocks[0].latest_resonance_level}`}
            className="resonance-detail-btn"
          >
            详情
          </Link>
        )}
      </div>
    </div>
    <StockList stocks={panel.stocks || []} />
  </section>
);

/* ─── Page ─── */

export default function SignalStatisticsPage() {
  const [dates, setDates] = useState([]);
  const [selectedDate, setSelectedDate] = useState("");
  const [panels, setPanels] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const loadStatistics = useCallback(async (tradeDate) => {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams();
      if (tradeDate) params.set("trade_date", tradeDate);
      const res = await apiFetch(`/daily-stock-signals/statistics?${params.toString()}`);
      if (!res.ok) throw new Error(`加载失败: ${res.status}`);
      const data = await res.json();
      setPanels(data.panels || []);
      if (data.trade_date) setSelectedDate(data.trade_date);
    } catch (err) {
      setError(err.message || "加载失败");
      setPanels([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const loadDates = async () => {
      try {
        const res = await apiFetch("/daily-stock-signals/dates");
        if (!res.ok) throw new Error("加载日期失败");
        const data = await res.json();
        const items = (data.items || []).map(normalizeDateValue).filter(Boolean);
        setDates(items);
        const firstDate = items[0] || "";
        if (firstDate) {
          setSelectedDate(firstDate);
          loadStatistics(firstDate);
        }
      } catch (err) {
        setError(err.message || "加载日期失败");
      }
    };
    loadDates();
  }, [loadStatistics]);

  return (
    <main className="page">
      <header className="header">
        <div>
          <p className="eyebrow">Quant Platform</p>
          <h1>信号统计</h1>
        </div>
      </header>

      <div className="toolbar">
        <form className="toolbar__left" onSubmit={(e) => { e.preventDefault(); loadStatistics(selectedDate); }}>
          <div className="field" style={{ marginBottom: 0 }}>
            <select id="tradeDate" value={selectedDate} onChange={(e) => setSelectedDate(e.target.value)}>
              <option value="">请选择日期</option>
              {dates.map((item) => <option key={item} value={item}>{formatDate(item)}</option>)}
            </select>
          </div>
          <button className="primary" type="submit" disabled={loading}>{loading ? "..." : "查询"}</button>
        </form>
      </div>

      {error ? <div className="error">{error}</div> : null}

      <div className="signal-card-stack">
        {panels.map((panel) => (
          <StatisticsPanel key={panel.id} panel={panel} />
        ))}
      </div>
    </main>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/pages/signal-statistics.js
git commit -m "feat: add signal statistics page"
```

---

## Task 4: 前端 - 增加导航入口和样式

**Files:**
- Modify: `frontend/pages/_app.js`
- Modify: `frontend/styles/globals.css`

- [ ] **Step 1: 在 _app.js 的 NAV 数组中增加"信号统计"**

找到 NAV 数组，添加：

```jsx
const NAV = [
  { label: "首页", href: "/" },
  { label: "信号", href: "/daily-signals" },
  { label: "信号统计", href: "/signal-statistics" },
  // ... 其他导航项
];
```

- [ ] **Step 2: 在 globals.css 中增加标签样式**

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

- [ ] **Step 3: Commit**

```bash
git add frontend/pages/_app.js
git add frontend/styles/globals.css
git commit -m "feat: add signal statistics navigation and styles"
```

---

## Task 5: 集成测试

- [ ] **Step 1: 启动后端服务**

```bash
cd backend
uvicorn app.main:app --reload --port 9000
```

- [ ] **Step 2: 启动前端服务**

```bash
cd frontend
npm run dev
```

- [ ] **Step 3: 测试 API**

```bash
curl "http://localhost:9000/api/daily-stock-signals/statistics"
```

预期返回：
```json
{
  "trade_date": "20250606",
  "panels": [
    {
      "id": "7d_2",
      "title": "过去7天出现≥2次买入共振",
      "count": 5,
      "stocks": [...]
    }
  ]
}
```

- [ ] **Step 4: 测试页面**

1. 打开 http://localhost:3000/freedom/signal-statistics
2. 确认日期选择器加载正常
3. 确认三个统计面板显示正确
4. 确认股票卡片显示共振次数
5. 点击"K线"跳转到股票详情页
6. 点击"详情"跳转到共振详情页

- [ ] **Step 5: Commit**

```bash
git commit -m "test: verify signal statistics feature"
```

---

## 自检清单

- [x] Spec coverage: 所有需求都有对应的任务
- [x] Placeholder scan: 无 TBD/TODO
- [x] Type consistency: 函数签名一致
- [x] API paths: 与 routers.py 中的注册一致
- [x] Cache: 使用 cache_set/cache_get
- [x] Error handling: 有错误处理

---

**Plan complete and saved to `docs/superpowers/plans/2026-06-07-signal-statistics.md`.**

**Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
