import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/router";
import { apiFetch } from "../../lib/api";

const formatDate = (value) => {
  if (!value) return "-";
  const s = String(value);
  return s.length === 8 ? `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}` : s;
};

const formatDateTime = (value) => {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(
    date.getDate()
  ).padStart(2, "0")} ${String(date.getHours()).padStart(2, "0")}:${String(
    date.getMinutes()
  ).padStart(2, "0")}`;
};

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

const formatMarketCap = (value) => {
  if (value === null || value === undefined || value === "") return "-";
  const num = Number(value);
  if (Number.isNaN(num) || num <= 0) return "-";
  const yi = num / 10000;
  if (yi >= 10000) return `${(yi / 10000).toFixed(2)} 万亿`;
  return `${yi.toFixed(0)} 亿`;
};

const SIGNAL_LABELS = {
  BUY: "买入",
  SELL: "卖出",
};

const getSignalLabel = (signal) => SIGNAL_LABELS[signal] || signal || "—";

/* ── Signal Detail Modal ── */
function SignalModal({ stock, onClose }) {
  const [signals, setSignals] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await apiFetch(`/daily-signals?stock_code=${encodeURIComponent(stock.ts_code)}`);
        if (res.ok) {
          const data = await res.json();
          if (!cancelled) setSignals(data.items || []);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [stock.ts_code]);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box modal-box--signal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-box__header">
          <h3>{stock.name || stock.ts_code} · 交易信号</h3>
          <button type="button" className="modal-box__close" onClick={onClose}>✕</button>
        </div>
        <div className="modal-box__body">
          {loading ? (
            <div className="loading-container"><div className="spinner"></div><p>加载中...</p></div>
          ) : signals.length === 0 ? (
            <div className="empty-state"><p>暂无信号记录</p></div>
          ) : (
            <table className="modal-table">
              <thead>
                <tr>
                  <th>日期</th>
                  <th>策略</th>
                  <th>信号</th>
                </tr>
              </thead>
              <tbody>
                {signals.map((s, i) => (
                  <tr key={i}>
                    <td>{formatDate(s.trading_date)}</td>
                    <td>{s.strategy || "-"}</td>
                    <td>
                      <span className={`change-pill ${s.signal === "BUY" ? "change-up" : "change-down"}`}>
                        {getSignalLabel(s.signal)}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}

/* ── Sortable column header ── */
function ThSort({ label, field, sortField, sortDir, onSort }) {
  const active = sortField === field;
  return (
    <th className="th-sortable" onClick={() => onSort(field)}>
      {label}
      <span className="sort-arrow">{active ? (sortDir === "asc" ? " ▲" : " ▼") : ""}</span>
    </th>
  );
}

/* ── Sort helper ── */
const SORT_FIELDS = ["total_mv", "latest_pct_chg", "pct_chg_3d", "pct_chg_5d"];

function sortItems(items, field, dir) {
  if (!field || !SORT_FIELDS.includes(field)) return items;
  return [...items].sort((a, b) => {
    const aVal = Number(a[field]) || 0;
    const bVal = Number(b[field]) || 0;
    return dir === "asc" ? aVal - bVal : bVal - aVal;
  });
}

export default function WatchlistGroupDetail() {
  const router = useRouter();
  const { groupId } = router.query;

  const [group, setGroup] = useState(null);
  const [items, setItems] = useState([]);
  const [codeInput, setCodeInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [editingRemark, setEditingRemark] = useState(null);
  const [remarkValue, setRemarkValue] = useState("");
  const [sortField, setSortField] = useState("");
  const [sortDir, setSortDir] = useState("desc");
  const [signalStock, setSignalStock] = useState(null);

  const loadGroup = async (id) => {
    const res = await apiFetch(`/stock-groups/${id}`);
    if (!res.ok) throw new Error(`加载失败: ${res.status}`);
    return res.json();
  };

  const loadStocks = async (id) => {
    const res = await apiFetch(`/stock-groups/${id}/stocks`);
    if (!res.ok) throw new Error(`加载失败: ${res.status}`);
    const data = await res.json();
    return data.items || [];
  };

  const refresh = async () => {
    if (!groupId) return;
    setLoading(true);
    try {
      const [groupData, stockItems] = await Promise.all([
        loadGroup(groupId),
        loadStocks(groupId),
      ]);
      setGroup(groupData);
      setItems(stockItems);
      setError("");
    } catch (err) {
      setError(err.message || "加载失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
  }, [groupId]);

  const handleSort = (field) => {
    if (sortField === field) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortField(field);
      setSortDir("desc");
    }
  };

  const displayedItems = sortItems(items, sortField, sortDir);

  const handleAdd = async (event) => {
    event.preventDefault();
    const trimmed = codeInput.trim();
    if (!trimmed || !groupId) {
      setError("请输入股票代码");
      return;
    }
    setSaving(true);
    setError("");
    try {
      const res = await apiFetch(`/stock-groups/${groupId}/stocks`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ts_code: trimmed }),
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        throw new Error(detail.detail || `添加失败: ${res.status}`);
      }
      setCodeInput("");
      await refresh();
    } catch (err) {
      setError(err.message || "添加失败");
    } finally {
      setSaving(false);
    }
  };

  const handleRemove = async (tsCode) => {
    if (!groupId) return;
    setSaving(true);
    setError("");
    try {
      const res = await apiFetch(`/stock-groups/${groupId}/stocks/${tsCode}`, {
        method: "DELETE",
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        throw new Error(detail.detail || `移除失败: ${res.status}`);
      }
      await refresh();
    } catch (err) {
      setError(err.message || "移除失败");
    } finally {
      setSaving(false);
    }
  };

  const handleRemarkSave = async (tsCode) => {
    if (!groupId) return;
    const trimmed = remarkValue.trim();
    setSaving(true);
    setError("");
    try {
      const res = await apiFetch(`/stock-groups/${groupId}/stocks/${tsCode}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ remark: trimmed }),
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        throw new Error(detail.detail || `更新失败: ${res.status}`);
      }
      setEditingRemark(null);
      await refresh();
    } catch (err) {
      setError(err.message || "更新失败");
    } finally {
      setSaving(false);
    }
  };

  const startEditRemark = (tsCode, currentRemark) => {
    setEditingRemark(tsCode);
    setRemarkValue(currentRemark || "");
  };

  const cancelEditRemark = () => {
    setEditingRemark(null);
    setRemarkValue("");
  };

  return (
    <main className="page">
      <header className="header">
        <div>
          <p className="eyebrow">Watchlist Group</p>
          <h1>{group?.name || "分组详情"}</h1>
          <p className="subtitle">创建时间：{formatDateTime(group?.created_at)}</p>
        </div>
        <Link href="/watchlist" className="link-button">
          ← 返回分组
        </Link>
      </header>

      <form className="filters" onSubmit={handleAdd}>
        <div className="field">
          <label htmlFor="stockCodeInput">添加股票</label>
          <input
            id="stockCodeInput"
            type="text"
            placeholder="例如 000001.SZ"
            value={codeInput}
            onChange={(event) => setCodeInput(event.target.value)}
          />
        </div>
        <button className="primary" type="submit" disabled={saving}>
          {saving ? "添加中..." : "加入分组"}
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
                <th>名称</th>
                <th>板块</th>
                <th>市场</th>
                <ThSort label="近1日涨跌" field="latest_pct_chg" sortField={sortField} sortDir={sortDir} onSort={handleSort} />
                <ThSort label="近3日涨跌" field="pct_chg_3d" sortField={sortField} sortDir={sortDir} onSort={handleSort} />
                <ThSort label="近5日涨跌" field="pct_chg_5d" sortField={sortField} sortDir={sortDir} onSort={handleSort} />
                <ThSort label="总市值" field="total_mv" sortField={sortField} sortDir={sortDir} onSort={handleSort} />
                <th>近期信号</th>
                <th className="th-remark">备注</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody className={loading ? "loading" : ""}>
              {items.length === 0 ? (
                <tr>
                  <td colSpan="12" className="empty">
                    <div className="empty-state">
                      <span className="empty-icon">🧷</span>
                      <p>暂无股票</p>
                      <small>输入股票代码添加到分组</small>
                    </div>
                  </td>
                </tr>
              ) : (
                displayedItems.map((item) => (
                  <tr key={item.ts_code}>
                    <td className="code-cell">{item.ts_code}</td>
                    <td className="name-cell">{item.name || "-"}</td>
                    <td>{item.industry ? <span className="badge">{item.industry}</span> : "-"}</td>
                    <td>{item.market ? <span className="market-badge">{item.market}</span> : "-"}</td>
                    <td>
                      <span className={`change-pill ${getChangeClass(item.latest_pct_chg)}`}>
                        {formatPct(item.latest_pct_chg)}
                      </span>
                    </td>
                    <td>
                      <span className={`change-pill ${getChangeClass(item.pct_chg_3d)}`}>
                        {formatPct(item.pct_chg_3d)}
                      </span>
                    </td>
                    <td>
                      <span className={`change-pill ${getChangeClass(item.pct_chg_5d)}`}>
                        {formatPct(item.pct_chg_5d)}
                      </span>
                    </td>
                    <td className="mv-cell">
                      <span className="mv-value">{formatMarketCap(item.total_mv)}</span>
                    </td>
                    <td className="signal-cell">
                      {item.latest_signal ? (
                        <span className={`signal-badge ${item.latest_signal === "BUY" ? "signal-buy" : "signal-sell"}`}>
                          {getSignalLabel(item.latest_signal)}
                        </span>
                      ) : (
                        <span className="signal-none">—</span>
                      )}
                      {item.latest_signal_date ? (
                        <span className="signal-date">{formatDate(item.latest_signal_date)}</span>
                      ) : null}
                    </td>
                    <td className="remark-cell">
                      {editingRemark === item.ts_code ? (
                        <div className="remark-edit">
                          <input
                            type="text"
                            value={remarkValue}
                            onChange={(e) => setRemarkValue(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === "Enter") handleRemarkSave(item.ts_code);
                              if (e.key === "Escape") cancelEditRemark();
                            }}
                            autoFocus
                            disabled={saving}
                            placeholder="输入备注..."
                          />
                          <div className="remark-edit-actions">
                            <button
                              type="button"
                              className="primary small"
                              onMouseDown={(e) => { e.preventDefault(); handleRemarkSave(item.ts_code); }}
                              disabled={saving}
                            >
                              保存
                            </button>
                            <button
                              type="button"
                              className="secondary small"
                              onMouseDown={(e) => { e.preventDefault(); cancelEditRemark(); }}
                              disabled={saving}
                            >
                              取消
                            </button>
                          </div>
                        </div>
                      ) : (
                        <span className="remark-text" title={item.remark || ""}>
                          {item.remark || "—"}
                        </span>
                      )}
                    </td>
                    <td className="action-cell">
                      <Link href={`/stocks/${item.ts_code}`} className="secondary small" style={{ textDecoration: "none" }}>
                        K线
                      </Link>
                      <button
                        type="button"
                        className="secondary small"
                        onClick={() => setSignalStock(item)}
                        disabled={saving}
                      >
                        信号
                      </button>
                      <button
                        type="button"
                        className="secondary small"
                        onClick={() => startEditRemark(item.ts_code, item.remark)}
                        disabled={saving}
                      >
                        编辑
                      </button>
                      <button
                        type="button"
                        className="danger-button small"
                        onClick={() => handleRemove(item.ts_code)}
                        disabled={saving}
                      >
                        移除
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        )}
      </section>

      {signalStock ? (
        <SignalModal stock={signalStock} onClose={() => setSignalStock(null)} />
      ) : null}
    </main>
  );
}
