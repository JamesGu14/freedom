import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { apiFetch } from "../../lib/api";

const formatPct = (value) => {
  if (value === null || value === undefined || value === "") return "-";
  const num = Number(value);
  if (Number.isNaN(num)) return "-";
  const prefix = num > 0 ? "+" : "";
  return `${prefix}${(num * 100).toFixed(2)}%`;
};

const formatDateTime = (value) => {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString();
};

export default function BacktestsPage() {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  const [status, setStatus] = useState("");
  const [strategyId, setStrategyId] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [paramsModalRun, setParamsModalRun] = useState(null);
  const [deletingRunId, setDeletingRunId] = useState("");

  const totalPages = useMemo(() => Math.max(Math.ceil(total / pageSize), 1), [total, pageSize]);

  const loadItems = async (targetPage = page) => {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams();
      params.set("page", String(targetPage));
      params.set("page_size", String(pageSize));
      if (status) params.set("status", status);
      if (strategyId.trim()) params.set("strategy_id", strategyId.trim());
      const res = await apiFetch(`/backtests?${params.toString()}`);
      if (!res.ok) throw new Error(`加载失败: ${res.status}`);
      const data = await res.json();
      setItems(data.items || []);
      setTotal(data.total || 0);
    } catch (err) {
      setError(err.message || "加载失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadItems();
  }, [page]);

  const handleSearch = (event) => {
    event.preventDefault();
    setPage(1);
    loadItems(1);
  };

  const showRunParams = (run) => {
    setParamsModalRun(run || null);
  };

  const closeRunParams = () => {
    setParamsModalRun(null);
  };

  const deleteRun = async (runId) => {
    if (!runId) return;
    const confirmed = window.confirm(`确认删除回测 Run ${runId} 吗？该操作会同时删除净值、交易、持仓、信号明细。`);
    if (!confirmed) return;
    setDeletingRunId(runId);
    setError("");
    try {
      const res = await apiFetch(`/backtests/${encodeURIComponent(runId)}`, {
        method: "DELETE",
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        throw new Error(detail.detail || `删除失败: ${res.status}`);
      }
      await loadItems(page);
    } catch (err) {
      setError(err.message || "删除失败");
    } finally {
      setDeletingRunId("");
    }
  };

  return (
    <main className="page">
      <header className="header">
        <div>
          <p className="eyebrow">Backtests</p>
          <h1>回测列表</h1>
          <p className="subtitle">查看所有 run 状态与核心指标</p>
        </div>
      </header>

      <form className="filters" onSubmit={handleSearch}>
        <label className="field">
          <span>状态</span>
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">全部</option>
            <option value="pending">pending</option>
            <option value="running">running</option>
            <option value="success">success</option>
            <option value="failed">failed</option>
          </select>
        </label>
        <label className="field">
          <span>策略ID</span>
          <input value={strategyId} onChange={(e) => setStrategyId(e.target.value)} placeholder="strategy_id" />
        </label>
        <div className="form-actions">
          <button className="primary" type="submit" disabled={loading}>
            {loading ? "查询中..." : "查询"}
          </button>
        </div>
      </form>

      {error ? <div className="error">{error}</div> : null}

      <section className="table-wrap compact-table backtests-table">
        <table>
          <thead>
            <tr>
              <th>Run ID</th>
              <th>版本</th>
              <th>变更说明</th>
              <th>状态</th>
              <th>区间</th>
              <th>累计收益</th>
              <th>创建时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 ? (
              <tr>
                <td colSpan={8} className="empty">
                  暂无数据
                </td>
              </tr>
            ) : (
              items.map((item) => (
                <tr key={item.run_id}>
                  <td>
                    <Link className="link-button" href={`/backtests/${item.run_id}`}>
                      {item.run_id}
                    </Link>
                  </td>
                  <td>{item.strategy_version_id}</td>
                  <td>{item.change_log || item?.strategy_version?.change_log || "-"}</td>
                  <td>{item.status}</td>
                  <td>
                    {item.start_date} ~ {item.end_date}
                  </td>
                  <td>{formatPct(item?.summary_metrics?.total_return)}</td>
                  <td>{formatDateTime(item.created_at)}</td>
                  <td>
                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                      <button type="button" className="link-button" onClick={() => showRunParams(item)}>
                        参数
                      </button>
                      <button
                        type="button"
                        className="danger-button"
                        onClick={() => deleteRun(item.run_id)}
                        disabled={deletingRunId === item.run_id}
                      >
                        {deletingRunId === item.run_id ? "删除中..." : "删除"}
                      </button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </section>

      <div className="pagination">
        <span>
          共 {total} 条，第 {page} / {totalPages} 页
        </span>
        <div className="pager-actions">
          <button type="button" disabled={page <= 1} onClick={() => setPage((v) => Math.max(v - 1, 1))}>
            上一页
          </button>
          <button
            type="button"
            disabled={page >= totalPages}
            onClick={() => setPage((v) => Math.min(v + 1, totalPages))}
          >
            下一页
          </button>
        </div>
      </div>

      {paramsModalRun ? (
        <div
          className="modal-backdrop"
          onClick={(event) => {
            if (event.target === event.currentTarget) closeRunParams();
          }}
        >
          <div className="modal-card">
            <div className="modal-header">
              <h3 style={{ margin: 0 }}>Run 参数快照</h3>
              <button type="button" className="link-button" onClick={closeRunParams}>
                关闭
              </button>
            </div>
            <div className="subtitle" style={{ marginBottom: 8 }}>
              {paramsModalRun.run_id}
            </div>
            <pre className="params-json">{JSON.stringify(paramsModalRun.params_snapshot || {}, null, 2)}</pre>
          </div>
        </div>
      ) : null}
    </main>
  );
}
