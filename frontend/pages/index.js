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

export default function Home() {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(10);
  const [nameQuery, setNameQuery] = useState("");
  const [codeQuery, setCodeQuery] = useState("");
  const [industry, setIndustry] = useState("");
  const [industries, setIndustries] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const loadStocks = async (overridePage) => {
    setError("");
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.set("page", String(overridePage || page));
      params.set("page_size", String(pageSize));
      if (nameQuery.trim()) {
        params.set("name", nameQuery.trim());
      }
      if (codeQuery.trim()) {
        params.set("ts_code", codeQuery.trim());
      }
      if (industry) {
        params.set("industry", industry);
      }
      const res = await apiFetch(`/stocks?${params.toString()}`);
      if (!res.ok) {
        throw new Error(`加载失败: ${res.status}`);
      }
      const data = await res.json();
      setItems(data.items || []);
      setTotal(data.total || 0);
    } catch (err) {
      setError(err.message || "加载失败");
    } finally {
      setLoading(false);
    }
  };

  const loadIndustries = async () => {
    try {
      const res = await apiFetch(`/stocks/industries`);
      if (!res.ok) {
        return;
      }
      const data = await res.json();
      setIndustries(data.items || []);
    } catch (err) {
      // ignore industry load failures
    }
  };

  const syncStocks = async () => {
    setError("");
    setLoading(true);
    try {
      const res = await apiFetch(`/stocks/sync`, {
        method: "POST",
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        throw new Error(detail.detail || `同步失败: ${res.status}`);
      }
      await loadStocks();
    } catch (err) {
      setError(err.message || "同步失败");
      setLoading(false);
    }
  };

  useEffect(() => {
    loadStocks();
  }, [page]);

  useEffect(() => {
    loadIndustries();
  }, []);

  const handleSearch = (event) => {
    event.preventDefault();
    setPage(1);
    loadStocks(1);
  };

  const totalPages = Math.max(Math.ceil(total / pageSize), 1);

  return (
    <main className="page">
      <header className="header">
        <div>
          <p className="eyebrow">Quant Platform</p>
          <h1>股票列表</h1>
          <p className="subtitle">来自 TuShare 的全市场基础信息</p>
        </div>
        <button className="primary sync-btn" onClick={syncStocks} disabled={loading} style={{ display: 'none' }}>
          {loading ? (
            <>
              <span className="btn-spinner"></span>
              <span>同步中...</span>
            </>
          ) : (
            <>
              <span>🔄</span>
              <span>获取最新列表</span>
            </>
          )}
        </button>
      </header>

      <form className="filters" onSubmit={handleSearch}>
        <div className="field">
          <label htmlFor="nameQuery">名称</label>
          <input
            id="nameQuery"
            type="text"
            placeholder="模糊搜索股票名称"
            value={nameQuery}
            onChange={(event) => setNameQuery(event.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="codeQuery">代码</label>
          <input
            id="codeQuery"
            type="text"
            placeholder="模糊搜索股票代码"
            value={codeQuery}
            onChange={(event) => setCodeQuery(event.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="industrySelect">行业</label>
          <select
            id="industrySelect"
            value={industry}
            onChange={(event) => setIndustry(event.target.value)}
          >
            <option value="">全部行业</option>
            {industries.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </div>
        <button className="primary" type="submit" disabled={loading}>
          {loading ? "搜索中..." : "搜索"}
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
                <th>代码</th>
                <th>名称</th>
                <th>行业</th>
                <th>市场</th>
                <th>近一日涨跌</th>
                <th>上市日期</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody className={loading ? "loading" : ""}>
              {items.length === 0 ? (
                <tr>
                  <td colSpan="7" className="empty">
                    <div className="empty-state">
                      <span className="empty-icon">📊</span>
                      <p>暂无数据</p>
                      <small>请使用搜索功能查找数据</small>
                    </div>
                  </td>
                </tr>
              ) : (
                items.map((item) => (
                  <tr key={item.ts_code}>
                    <td className="code-cell">{item.ts_code}</td>
                    <td className="name-cell">{item.name}</td>
                    <td>
                      {item.industry ? (
                        <span className="badge">{item.industry}</span>
                      ) : (
                        "-"
                      )}
                    </td>
                    <td>
                      {item.market ? (
                        <span className="market-badge">{item.market}</span>
                      ) : (
                        "-"
                      )}
                    </td>
                    <td title={item.latest_trade_date || ""}>
                      <span className={`change-pill ${getChangeClass(item.latest_pct_chg)}`}>
                        {formatPct(item.latest_pct_chg)}
                      </span>
                    </td>
                    <td>{item.list_date || "-"}</td>
                    <td>
                      <Link className="link-button" href={`/stocks/${item.ts_code}`}>
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
            onClick={() => setPage((current) => Math.max(current - 1, 1))}
            disabled={loading || page <= 1}
          >
            上一页
          </button>
          <button
            type="button"
            onClick={() => setPage((current) => Math.min(current + 1, totalPages))}
            disabled={loading || page >= totalPages}
          >
            下一页
          </button>
        </div>
      </div>
    </main>
  );
}
