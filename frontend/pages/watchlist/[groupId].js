import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/router";
import { apiFetch } from "../../lib/api";

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

export default function WatchlistGroupDetail() {
  const router = useRouter();
  const { groupId } = router.query;

  const [group, setGroup] = useState(null);
  const [items, setItems] = useState([]);
  const [codeInput, setCodeInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const loadGroup = async (id) => {
    const res = await apiFetch(`/stock-groups/${id}`);
    if (!res.ok) {
      throw new Error(`加载失败: ${res.status}`);
    }
    return res.json();
  };

  const loadStocks = async (id) => {
    const res = await apiFetch(`/stock-groups/${id}/stocks`);
    if (!res.ok) {
      throw new Error(`加载失败: ${res.status}`);
    }
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
                <th>近一日涨跌</th>
                <th>加入时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody className={loading ? "loading" : ""}>
              {items.length === 0 ? (
                <tr>
                  <td colSpan="7" className="empty">
                    <div className="empty-state">
                      <span className="empty-icon">🧷</span>
                      <p>暂无股票</p>
                      <small>输入股票代码添加到分组</small>
                    </div>
                  </td>
                </tr>
              ) : (
                items.map((item) => (
                  <tr key={item.ts_code}>
                    <td className="code-cell">{item.ts_code}</td>
                    <td className="name-cell">{item.name || "-"}</td>
                    <td>{item.industry ? <span className="badge">{item.industry}</span> : "-"}</td>
                    <td>{item.market ? <span className="market-badge">{item.market}</span> : "-"}</td>
                    <td title={item.latest_trade_date || ""}>
                      <span className={`change-pill ${getChangeClass(item.latest_pct_chg)}`}>
                        {formatPct(item.latest_pct_chg)}
                      </span>
                    </td>
                    <td>{formatDateTime(item.added_at)}</td>
                    <td>
                      <button
                        type="button"
                        className="danger-button"
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
    </main>
  );
}
