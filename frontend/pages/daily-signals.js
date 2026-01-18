import { useEffect, useState } from "react";
import Link from "next/link";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:9000/api";

const formatDate = (value) => {
  if (!value || value.length !== 8) return value || "-";
  return `${value.slice(0, 4)}-${value.slice(4, 6)}-${value.slice(6, 8)}`;
};

export default function DailySignals() {
  const [dates, setDates] = useState([]);
  const [selectedDate, setSelectedDate] = useState("");
  const [stockCode, setStockCode] = useState("");
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [hasQuery, setHasQuery] = useState(false);

  const loadDates = async () => {
    try {
      const res = await fetch(`${API_BASE}/daily-signals/dates`);
      if (!res.ok) {
        return;
      }
      const data = await res.json();
      const items = [...(data.items || [])].sort((a, b) => String(b).localeCompare(String(a)));
      setDates(items);
      if (items.length > 0) {
        setSelectedDate(items[0]);
        loadSignals(items[0], stockCode);
      }
    } catch (err) {
      // ignore date load failures
    }
  };

  const loadSignals = async (overrideDate, overrideStock) => {
    setError("");
    const dateValue = overrideDate ?? selectedDate;
    const stockValue = overrideStock ?? stockCode;
    if (!dateValue && !stockValue.trim()) {
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
      const res = await fetch(`${API_BASE}/daily-signals?${params.toString()}`);
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
  }, []);

  const handleSubmit = (event) => {
    event.preventDefault();
    loadSignals();
  };

  return (
    <main className="page">
      <header className="header">
        <div>
          <p className="eyebrow">Quant Platform</p>
          <h1>每日信号</h1>
          <p className="subtitle">查看策略产生的 BUY 信号记录</p>
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
                <th>交易日期</th>
                <th>信号</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody className={loading ? "loading" : ""}>
              {items.length === 0 ? (
                <tr>
                  <td colSpan="4" className="empty">
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
                    <td>{formatDate(item.trading_date)}</td>
                    <td>
                      <span className="badge">{item.signal || "BUY"}</span>
                    </td>
                    <td>
                      <Link
                        className="link-button"
                        href={`/stocks/${item.stock_code}`}
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
