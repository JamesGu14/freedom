import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/router";
import { apiFetch } from "../lib/api";

const STRATEGY_PORTFOLIO_ID = "__strategy__";

const SIGNAL_OPTIONS = [
  { value: "", label: "全部" },
  { value: "BUY", label: "BUY" },
  { value: "SELL", label: "SELL" },
  { value: "HOLD", label: "HOLD" },
  { value: "BUY_ROTATE", label: "BUY_ROTATE" },
  { value: "SELL_ROTATE", label: "SELL_ROTATE" },
];

const PORTFOLIO_TYPE_OPTIONS = [
  { value: "strategy", label: "策略级" },
];

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

const formatNumber = (value) => {
  if (value === null || value === undefined || value === "") return "-";
  const num = Number(value);
  if (Number.isNaN(num)) return String(value);
  return num.toLocaleString("zh-CN", { maximumFractionDigits: 2 });
};

const formatScore = (value) => {
  if (value === null || value === undefined || value === "") return "-";
  const num = Number(value);
  if (Number.isNaN(num)) return "-";
  return num.toFixed(2);
};

const formatWeight = (value) => {
  if (value === null || value === undefined || value === "") return "-";
  const num = Number(value);
  if (Number.isNaN(num)) return "-";
  return `${(num * 100).toFixed(2)}%`;
};

const signalBadgeClass = (signal) => {
  const value = String(signal || "").toUpperCase();
  if (value.includes("BUY")) return "badge signal-badge signal-badge-buy";
  if (value.includes("SELL")) return "badge signal-badge signal-badge-sell";
  return "badge signal-badge signal-badge-hold";
};

export default function StrategySignalsPage() {
  const router = useRouter();
  const [dates, setDates] = useState([]);
  const [dateSet, setDateSet] = useState(new Set());
  const [selectedDate, setSelectedDate] = useState("");
  const [strategyVersionId, setStrategyVersionId] = useState("");
  const [signal, setSignal] = useState("");
  const [portfolioType, setPortfolioType] = useState("strategy");
  const [calendarMonth, setCalendarMonth] = useState(() => {
    const now = new Date();
    return new Date(now.getFullYear(), now.getMonth(), 1);
  });
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [hasQuery, setHasQuery] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(50);
  const [total, setTotal] = useState(0);
  const [returnUrl, setReturnUrl] = useState("/daily-signals");

  useEffect(() => {
    if (router.isReady) {
      setReturnUrl(router.asPath);
    }
  }, [router.asPath, router.isReady]);

  const totalPages = useMemo(() => {
    const count = Math.max(Math.ceil(total / pageSize), 1);
    return count;
  }, [total, pageSize]);

  const loadSignals = async (override = {}) => {
    setError("");
    const dateValue = override.date ?? selectedDate;
    const pageValue = override.page ?? page;
    const strategyVersionValue = (override.strategyVersionId ?? strategyVersionId).trim();
    const signalValue = override.signal ?? signal;
    const portfolioTypeValue = override.portfolioType ?? portfolioType;

    if (!dateValue) {
      setItems([]);
      setTotal(0);
      setHasQuery(false);
      return;
    }

    setHasQuery(true);
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.set("signal_date", dateValue);
      params.set("portfolio_id", STRATEGY_PORTFOLIO_ID);
      params.set("portfolio_type", portfolioTypeValue);
      params.set("page", String(pageValue));
      params.set("page_size", String(pageSize));
      if (strategyVersionValue) params.set("strategy_version_id", strategyVersionValue);
      if (signalValue) params.set("signal", signalValue);

      const res = await apiFetch(`/strategy-signals?${params.toString()}`);
      if (!res.ok) {
        throw new Error(`加载失败: ${res.status}`);
      }
      const data = await res.json();
      setItems(data.items || []);
      setTotal(data.total || 0);
    } catch (err) {
      setError(err.message || "加载失败");
      setItems([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  };

  const loadDates = async (overrideVersionId = "") => {
    try {
      const params = new URLSearchParams();
      params.set("portfolio_id", STRATEGY_PORTFOLIO_ID);
      const versionId = String(overrideVersionId || "").trim();
      if (versionId) params.set("strategy_version_id", versionId);
      const res = await apiFetch(`/strategy-signals/dates?${params.toString()}`);
      if (!res.ok) {
        return;
      }
      const data = await res.json();
      const rawItems = data.items || [];
      const normalizedItems = rawItems
        .map((item) => normalizeDateValue(item))
        .filter((item) => item);
      const nextDates = [...new Set(normalizedItems)].sort((a, b) => String(b).localeCompare(String(a)));
      setDates(nextDates);
      setDateSet(new Set(nextDates));

      if (!nextDates.length) {
        setSelectedDate("");
        setItems([]);
        setTotal(0);
        return;
      }

      const keepCurrent = selectedDate && nextDates.includes(selectedDate);
      const nextSelectedDate = keepCurrent ? selectedDate : nextDates[0];
      setSelectedDate(nextSelectedDate);
      const latest = parseYmd(nextSelectedDate);
      if (latest) {
        setCalendarMonth(new Date(latest.getFullYear(), latest.getMonth(), 1));
      }
      setPage(1);
      loadSignals({ date: nextSelectedDate, page: 1, strategyVersionId: versionId });
    } catch (err) {
      // ignore date load failures
    }
  };

  useEffect(() => {
    loadDates("");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSubmit = (event) => {
    event.preventDefault();
    setPage(1);
    loadSignals({ page: 1 });
  };

  const handleVersionChange = (value) => {
    setStrategyVersionId(value);
    setPage(1);
    loadDates(value);
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
    const year = parseInt(event.target.value, 10);
    if (!calendarMonth || Number.isNaN(year)) return;
    const newMonth = new Date(calendarMonth);
    newMonth.setFullYear(year);
    setCalendarMonth(newMonth);
  };

  const handleMonthChange = (event) => {
    const month = parseInt(event.target.value, 10);
    if (!calendarMonth || Number.isNaN(month)) return;
    const newMonth = new Date(calendarMonth);
    newMonth.setMonth(month);
    setCalendarMonth(newMonth);
  };

  return (
    <main className="page">
      <header className="header">
        <div>
          <p className="eyebrow">Quant Platform</p>
          <h1>Daily Signals</h1>
          <p className="subtitle">策略级每日信号（新）</p>
        </div>
        <div className="calendar-panel">
          <div className="calendar-header">
            <span>信号日历</span>
            <div className="calendar-controls">
              <button type="button" className="calendar-nav-btn" onClick={() => changeYear(-1)} title="上一年">
                ««
              </button>
              <button type="button" className="calendar-nav-btn" onClick={() => changeMonth(-1)} title="上一个月">
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
              <button type="button" className="calendar-nav-btn" onClick={() => changeMonth(1)} title="下一个月">
                ›
              </button>
              <button type="button" className="calendar-nav-btn" onClick={() => changeYear(1)} title="下一年">
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
            {(calendarMonth ? buildCalendar(calendarMonth.getFullYear(), calendarMonth.getMonth()) : []).map((day, idx) => {
              if (!day) {
                return <div key={`empty-${idx}`} className="calendar-cell calendar-empty"></div>;
              }
              const key = `${day.getFullYear()}${String(day.getMonth() + 1).padStart(2, "0")}${String(day.getDate()).padStart(2, "0")}`;
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
                      setPage(1);
                      loadSignals({ date: key, page: 1 });
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
          <label htmlFor="signalDateSelect">信号日期</label>
          <select
            id="signalDateSelect"
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
          <label htmlFor="strategyVersionId">策略版本</label>
          <input
            id="strategyVersionId"
            type="text"
            placeholder="例如 alpha-xxxx:v3"
            value={strategyVersionId}
            onChange={(event) => handleVersionChange(event.target.value)}
          />
        </div>

        <div className="field">
          <label htmlFor="portfolioType">组合类型</label>
          <select
            id="portfolioType"
            value={portfolioType}
            onChange={(event) => setPortfolioType(event.target.value)}
          >
            {PORTFOLIO_TYPE_OPTIONS.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        </div>

        <div className="field">
          <label htmlFor="signalType">信号</label>
          <select id="signalType" value={signal} onChange={(event) => setSignal(event.target.value)}>
            {SIGNAL_OPTIONS.map((item) => (
              <option key={item.label} value={item.value}>
                {item.label}
              </option>
            ))}
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
                <th>信号日</th>
                <th>计划成交日</th>
                <th>策略版本</th>
                <th>代码</th>
                <th>名称</th>
                <th>信号</th>
                <th>分数</th>
                <th>排名</th>
                <th>目标仓位</th>
                <th>目标金额</th>
                <th>市场状态</th>
                <th>原因</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody className={loading ? "loading" : ""}>
              {items.length === 0 ? (
                <tr>
                  <td colSpan="13" className="empty">
                    <div className="empty-state">
                      <p>{hasQuery ? "暂无符合条件的数据" : "请选择信号日期进行查询"}</p>
                    </div>
                  </td>
                </tr>
              ) : (
                items.map((item, idx) => (
                  <tr key={`${item.signal_date}-${item.strategy_version_id}-${item.ts_code}-${idx}`}>
                    <td>{formatDate(item.signal_date)}</td>
                    <td>{formatDate(item.signal_trade_date)}</td>
                    <td>{item.strategy_version_id || "-"}</td>
                    <td className="code-cell">{item.ts_code || "-"}</td>
                    <td>{item.stock_name || "-"}</td>
                    <td>
                      <span className={signalBadgeClass(item.signal)}>{item.signal || "HOLD"}</span>
                    </td>
                    <td>{formatScore(item.score)}</td>
                    <td>{item.rank || "-"}</td>
                    <td>{formatWeight(item.target_weight)}</td>
                    <td>{formatNumber(item.target_amount)}</td>
                    <td>{item.market_regime || "-"}</td>
                    <td>{Array.isArray(item.reason_codes) ? item.reason_codes.join(", ") : "-"}</td>
                    <td>
                      <Link
                        className="link-button"
                        href={`/stocks/${item.ts_code}?returnUrl=${encodeURIComponent(returnUrl)}`}
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

      <div className="pagination">
        <span>
          共 {total} 条，第 {page} / {totalPages} 页
        </span>
        <div className="pager-actions">
          <button
            type="button"
            onClick={() => {
              const nextPage = Math.max(page - 1, 1);
              setPage(nextPage);
              loadSignals({ page: nextPage });
            }}
            disabled={loading || page <= 1}
          >
            上一页
          </button>
          <button
            type="button"
            onClick={() => {
              const nextPage = Math.min(page + 1, totalPages);
              setPage(nextPage);
              loadSignals({ page: nextPage });
            }}
            disabled={loading || page >= totalPages}
          >
            下一页
          </button>
        </div>
      </div>
    </main>
  );
}
