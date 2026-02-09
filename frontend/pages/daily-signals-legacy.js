import { useEffect, useState } from "react";
import Link from "next/link";
import { apiFetch } from "../lib/api";

const formatPct = (value) => {
  if (value === null || value === undefined || value === "") return "-";
  const num = Number(value);
  if (Number.isNaN(num)) return String(value);
  const prefix = num > 0 ? "+" : "";
  return `${prefix}${num.toFixed(2)}%`;
};

const getChangeClass = (value) => {
  const num = Number(value);
  if (Number.isNaN(num)) return "change-flat";
  if (num > 0) return "change-up";
  if (num < 0) return "change-down";
  return "change-flat";
};

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

const parseYmd = (value) => {
  const normalized = normalizeDateValue(value);
  if (!normalized) return null;
  const year = Number(normalized.slice(0, 4));
  const month = Number(normalized.slice(4, 6)) - 1;
  const day = Number(normalized.slice(6, 8));
  return new Date(year, month, day);
};

const buildCalendar = (year, monthIndex) => {
  const firstDay = new Date(year, monthIndex, 1);
  const startWeekday = firstDay.getDay();
  const daysInMonth = new Date(year, monthIndex + 1, 0).getDate();
  const cells = [];
  for (let i = 0; i < startWeekday; i += 1) {
    cells.push(null);
  }
  for (let day = 1; day <= daysInMonth; day += 1) {
    cells.push(new Date(year, monthIndex, day));
  }
  while (cells.length % 7 !== 0) {
    cells.push(null);
  }
  return cells;
};

import { useRouter } from "next/router";

export default function DailySignalsLegacy() {
  const router = useRouter();
  const [dates, setDates] = useState([]);
  const [dateSet, setDateSet] = useState(new Set());
  const [selectedDate, setSelectedDate] = useState("");
  const [stockCode, setStockCode] = useState("");
  const [strategy, setStrategy] = useState("");
  const [signal, setSignal] = useState("");
  const [strategies, setStrategies] = useState([]);
  const [calendarMonth, setCalendarMonth] = useState(() => {
    const now = new Date();
    return new Date(now.getFullYear(), now.getMonth(), 1);
  });
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [hasQuery, setHasQuery] = useState(false);
  const [returnUrl, setReturnUrl] = useState("/daily-signals-legacy");

  useEffect(() => {
    // 使用 router.asPath 获取不带 basePath 的路径（包括查询参数）
    if (router.isReady) {
      setReturnUrl(router.asPath);
    }
  }, [router.asPath, router.isReady]);

  const loadDates = async () => {
    try {
      const res = await apiFetch(`/daily-signals/dates`);
      if (!res.ok) {
        return;
      }
      const data = await res.json();
      const rawItems = data.items || [];
      const normalizedItems = rawItems
        .map((item) => normalizeDateValue(item))
        .filter((item) => item);
      const items = [...new Set(normalizedItems)].sort((a, b) => String(b).localeCompare(String(a)));
      setDates(items);
      setDateSet(new Set(items));
      if (items.length > 0 && !selectedDate) {
        setSelectedDate(items[0]);
        loadSignals(items[0], stockCode, strategy, signal);
        const latest = parseYmd(items[0]);
        if (latest) {
          setCalendarMonth(new Date(latest.getFullYear(), latest.getMonth(), 1));
        }
      }
    } catch (err) {
      // ignore date load failures
    }
  };

  const loadStrategies = async () => {
    try {
      const res = await apiFetch(`/daily-signals/strategies`);
      if (!res.ok) {
        return;
      }
      const data = await res.json();
      setStrategies(data.items || []);
    } catch (err) {
      // ignore strategy load failures
    }
  };

  const loadSignals = async (overrideDate, overrideStock, overrideStrategy, overrideSignal) => {
    setError("");
    const dateValue = overrideDate ?? selectedDate;
    const stockValue = overrideStock ?? stockCode;
    const strategyValue = overrideStrategy ?? strategy;
    const signalValue = overrideSignal ?? signal;
    if (!dateValue && !stockValue.trim() && !strategyValue.trim() && !signalValue.trim()) {
      setItems([]);
      setHasQuery(false);
      return;
    }
    setHasQuery(true);
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (dateValue) params.set("trading_date", dateValue);
      if (stockValue.trim()) params.set("stock_code", stockValue.trim());
      if (strategyValue.trim()) params.set("strategy", strategyValue.trim());
      if (signalValue.trim()) params.set("signal", signalValue.trim());
      const res = await apiFetch(`/daily-signals?${params.toString()}`);
      if (!res.ok) {
        throw new Error(`加载失败: ${res.status}`);
      }
      const data = await res.json();
      setItems(data.items || []);
    } catch (err) {
      setError(err.message || "加载失败");
      setItems([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDates();
    loadStrategies();
  }, []);

  const handleSubmit = (event) => {
    event.preventDefault();
    loadSignals();
  };

  const changeMonth = (delta) => {
    if (!calendarMonth) return;
    const newMonth = new Date(calendarMonth);
    newMonth.setMonth(newMonth.getMonth() + delta);
    setCalendarMonth(newMonth);
  };

  const changeYear = (delta) => {
    if (!calendarMonth) return;
    const newMonth = new Date(calendarMonth);
    newMonth.setFullYear(newMonth.getFullYear() + delta);
    setCalendarMonth(newMonth);
  };

  const handleYearChange = (event) => {
    const year = parseInt(event.target.value);
    if (!calendarMonth) return;
    const newMonth = new Date(calendarMonth);
    newMonth.setFullYear(year);
    setCalendarMonth(newMonth);
  };

  const handleMonthChange = (event) => {
    const month = parseInt(event.target.value);
    if (!calendarMonth) return;
    const newMonth = new Date(calendarMonth);
    newMonth.setMonth(month);
    setCalendarMonth(newMonth);
  };

  return (
    <main className="page">
      <header className="header">
        <div>
          <p className="eyebrow">Quant Platform</p>
          <h1>Daily Signals(旧)</h1>
          <p className="subtitle">旧版 daily_signal 页面，后续将下线</p>
        </div>
        <div className="calendar-panel">
          <div className="calendar-header">
            <span>信号日历</span>
            <div className="calendar-controls">
              <button
                type="button"
                className="calendar-nav-btn"
                onClick={() => changeYear(-1)}
                title="上一年"
              >
                ««
              </button>
              <button
                type="button"
                className="calendar-nav-btn"
                onClick={() => changeMonth(-1)}
                title="上一个月"
              >
                ‹
              </button>
              <select
                className="calendar-year-select"
                value={calendarMonth ? calendarMonth.getFullYear() : new Date().getFullYear()}
                onChange={handleYearChange}
              >
                {Array.from({ length: 10 }, (_, i) => {
                  const year = new Date().getFullYear() - 5 + i;
                  return (
                    <option key={year} value={year}>
                      {year}年
                    </option>
                  );
                })}
              </select>
              <select
                className="calendar-month-select"
                value={calendarMonth ? calendarMonth.getMonth() : new Date().getMonth()}
                onChange={handleMonthChange}
              >
                {Array.from({ length: 12 }, (_, i) => (
                  <option key={i} value={i}>
                    {i + 1}月
                  </option>
                ))}
              </select>
              <button
                type="button"
                className="calendar-nav-btn"
                onClick={() => changeMonth(1)}
                title="下一个月"
              >
                ›
              </button>
              <button
                type="button"
                className="calendar-nav-btn"
                onClick={() => changeYear(1)}
                title="下一年"
              >
                »»
              </button>
            </div>
          </div>
          <div className="calendar-grid">
            {["日", "一", "二", "三", "四", "五", "六"].map((label) => (
              <div key={label} className="calendar-weekday">
                {label}
              </div>
            ))}
            {(calendarMonth
              ? buildCalendar(calendarMonth.getFullYear(), calendarMonth.getMonth())
              : []
            ).map((day, idx) => {
              if (!day) {
                return <div key={`empty-${idx}`} className="calendar-cell calendar-empty"></div>;
              }
              const key = `${day.getFullYear()}${String(day.getMonth() + 1).padStart(2, "0")}${String(
                day.getDate()
              ).padStart(2, "0")}`;
              const hasSignal = dateSet.has(key);
              const isSelected = selectedDate === key;
              return (
                <div
                  key={key}
                  className={`calendar-cell${hasSignal ? " active" : ""}${isSelected ? " selected" : ""}`}
                  title={formatDate(key)}
                  onClick={() => {
                    if (hasSignal) {
                      setSelectedDate(key);
                      loadSignals(key, stockCode, strategy, signal);
                    }
                  }}
                  style={{ cursor: hasSignal ? "pointer" : "default" }}
                >
                  {day.getDate()}
                </div>
              );
            })}
          </div>
        </div>
      </header>

      <form className="filters" onSubmit={handleSubmit}>
        <div className="field">
          <label htmlFor="dateSelect">交易日期</label>
          <select
            id="dateSelect"
            value={selectedDate}
            onChange={(event) => setSelectedDate(event.target.value)}
          >
            <option value="">请选择日期</option>
            {dates.map((item) => (
              <option key={item} value={item}>
                {formatDate(item)}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="stockCode">股票代码</label>
          <input
            id="stockCode"
            type="text"
            placeholder="例如 000001.SZ"
            value={stockCode}
            onChange={(event) => setStockCode(event.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="strategy">策略名</label>
          <select
            id="strategy"
            value={strategy}
            onChange={(event) => setStrategy(event.target.value)}
          >
            <option value="">全部策略</option>
            {strategies.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="signal">信号</label>
          <select
            id="signal"
            value={signal}
            onChange={(event) => setSignal(event.target.value)}
          >
            <option value="">全部</option>
            <option value="BUY">BUY</option>
            <option value="SELL">SELL</option>
          </select>
        </div>
        <button className="primary" type="submit" disabled={loading}>
          {loading ? "查询中..." : "查询"}
        </button>
      </form>

      {error ? <div className="error">{error}</div> : null}

      <section className="table-wrap">
        {loading && items.length === 0 ? (
          <div className="loading-container">
            <div className="spinner"></div>
            <p>加载中...</p>
          </div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>股票代码</th>
                <th>股票名称</th>
                <th>交易日期</th>
                <th>当日涨跌</th>
                <th>策略名</th>
                <th>信号</th>
                <th>板块</th>
                <th>下一日涨跌</th>
                <th>自选组</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody className={loading ? "loading" : ""}>
              {items.length === 0 ? (
                <tr>
                  <td colSpan="10" className="empty">
                    <div className="empty-state">
                      <span className="empty-icon">📌</span>
                      <p>
                        {hasQuery
                          ? "暂无符合条件的数据"
                          : "请选择日期或股票代码进行查询"}
                      </p>
                    </div>
                  </td>
                </tr>
              ) : (
                items.map((item, idx) => (
                  <tr key={`${item.stock_code}-${item.strategy}-${idx}`}>
                    <td className="code-cell">{item.stock_code}</td>
                    <td>{item.name || "-"}</td>
                    <td>{formatDate(item.trading_date)}</td>
                    <td>
                      {item.current_pct_chg === null || item.current_pct_chg === undefined ? (
                        <span className="muted-text">-</span>
                      ) : (
                        <span className={`change-pill ${getChangeClass(item.current_pct_chg)}`}>
                          {formatPct(item.current_pct_chg)}
                        </span>
                      )}
                    </td>
                    <td>{item.strategy || "-"}</td>
                    <td>
                      <span className="badge">{item.signal || "BUY"}</span>
                    </td>
                    <td>{item.industry ? <span className="badge">{item.industry}</span> : "-"}</td>
                    <td>
                      {item.next_pct_chg === null || item.next_pct_chg === undefined ? (
                        <span className="muted-text">暂无数据</span>
                      ) : (
                        <div className="next-day-info">
                          <span className={`change-pill ${getChangeClass(item.next_pct_chg)}`}>
                            {formatPct(item.next_pct_chg)}
                          </span>
                          {item.next_trade_date && (
                            <span className="next-date-label">
                              {formatDate(item.next_trade_date)}
                            </span>
                          )}
                        </div>
                      )}
                    </td>
                    <td>
                      {item.groups && item.groups.length > 0 ? (
                        <div className="group-tags">
                          {item.groups.map((group) => (
                            <span key={group} className="group-tag">
                              {group}
                            </span>
                          ))}
                        </div>
                      ) : (
                        "-"
                      )}
                    </td>
                    <td>
                      <Link
                        className="link-button"
                        href={`/stocks/${item.stock_code}?returnUrl=${encodeURIComponent(returnUrl)}`}
                      >
                        查看K线
                      </Link>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        )}
      </section>
    </main>
  );
}
