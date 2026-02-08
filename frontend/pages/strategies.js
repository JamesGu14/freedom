import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/router";
import { apiFetch } from "../lib/api";

const formatDateTime = (value) => {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString();
};

const formatPct = (value) => {
  if (value === null || value === undefined || value === "") return "-";
  const num = Number(value);
  if (Number.isNaN(num)) return "-";
  const prefix = num > 0 ? "+" : "";
  return `${prefix}${(num * 100).toFixed(2)}%`;
};

export default function StrategiesPage() {
  const router = useRouter();
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const [selectedStrategyId, setSelectedStrategyId] = useState("");
  const [versions, setVersions] = useState([]);
  const [runs, setRuns] = useState([]);
  const [selectedRunIds, setSelectedRunIds] = useState([]);

  const [newName, setNewName] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [newOwner, setNewOwner] = useState("");

  const [selectedVersionId, setSelectedVersionId] = useState("");
  const [versionCodeRef, setVersionCodeRef] = useState("main");
  const [versionChangeLog, setVersionChangeLog] = useState("");
  const [paramsText, setParamsText] = useState(
    JSON.stringify(
      {
        strategy_key: "multifactor_v1",
        score_direction: "reverse",
        buy_threshold: 82,
        sell_threshold: 42,
        max_positions: 5,
        slot_weight: 0.2,
        sector_max: 0.45,
        min_avg_amount_20d: 25000,
        market_exposure: { risk_on: 1.0, neutral: 0.85, risk_off: 0.3 },
        stop_loss_pct: 0.1,
        trail_stop_pct: 0.12,
        max_hold_days: 60,
        sell_confirm_days: 3,
        rotate_score_delta: 15,
        rotate_profit_ceiling: 0.02,
        min_hold_days_before_rotate: 8,
        allowed_boards: ["sh_main", "sz_main", "star", "gem"],
        enable_buy_tech_filter: false,
        signal_store_topk: 100,
      },
      null,
      2
    )
  );

  const [runStartDate, setRunStartDate] = useState("20250101");
  const [runEndDate, setRunEndDate] = useState("20260206");
  const [runType, setRunType] = useState("range");
  const [runCreating, setRunCreating] = useState(false);
  const [paramsModalRun, setParamsModalRun] = useState(null);
  const [deletingRunId, setDeletingRunId] = useState("");

  const totalPages = useMemo(() => Math.max(Math.ceil(total / pageSize), 1), [total, pageSize]);

  const loadStrategies = async (targetPage = page) => {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams();
      params.set("page", String(targetPage));
      params.set("page_size", String(pageSize));
      const res = await apiFetch(`/strategies?${params.toString()}`);
      if (!res.ok) throw new Error(`加载策略失败: ${res.status}`);
      const data = await res.json();
      const list = data.items || [];
      setItems(list);
      setTotal(data.total || 0);
      if (!selectedStrategyId && list.length > 0) {
        setSelectedStrategyId(list[0].strategy_id);
      }
    } catch (err) {
      setError(err.message || "加载策略失败");
    } finally {
      setLoading(false);
    }
  };

  const loadStrategyDetails = async (strategyId) => {
    if (!strategyId) return;
    try {
      const [versionRes, runRes] = await Promise.all([
        apiFetch(`/strategies/${strategyId}/versions`),
        apiFetch(`/backtests?strategy_id=${encodeURIComponent(strategyId)}&page=1&page_size=100`),
      ]);
      if (!versionRes.ok) throw new Error(`加载版本失败: ${versionRes.status}`);
      if (!runRes.ok) throw new Error(`加载回测失败: ${runRes.status}`);
      const versionData = await versionRes.json();
      const runData = await runRes.json();
      const versionItems = versionData.items || [];
      setVersions(versionItems);
      setRuns(runData.items || []);
      setSelectedRunIds([]);
      if (versionItems.length > 0) {
        setSelectedVersionId((prev) =>
          versionItems.find((item) => item.strategy_version_id === prev)
            ? prev
            : versionItems[0].strategy_version_id
        );
      } else {
        setSelectedVersionId("");
      }
    } catch (err) {
      setError(err.message || "加载详情失败");
    }
  };

  useEffect(() => {
    loadStrategies();
  }, [page]);

  useEffect(() => {
    if (!selectedStrategyId) return;
    loadStrategyDetails(selectedStrategyId);
  }, [selectedStrategyId]);

  const createStrategy = async (event) => {
    event.preventDefault();
    setError("");
    try {
      const res = await apiFetch("/strategies", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: newName.trim(),
          description: newDescription.trim(),
          owner: newOwner.trim(),
        }),
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        throw new Error(detail.detail || `创建失败: ${res.status}`);
      }
      const item = await res.json();
      setNewName("");
      setNewDescription("");
      setNewOwner("");
      await loadStrategies(1);
      setPage(1);
      setSelectedStrategyId(item.strategy_id);
    } catch (err) {
      setError(err.message || "创建失败");
    }
  };

  const createVersion = async (event) => {
    event.preventDefault();
    if (!selectedStrategyId) return;
    setError("");
    let paramsSnapshot = {};
    try {
      paramsSnapshot = JSON.parse(paramsText || "{}");
    } catch (err) {
      setError("params_snapshot 不是合法 JSON");
      return;
    }
    try {
      const res = await apiFetch(`/strategies/${selectedStrategyId}/versions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          params_snapshot: paramsSnapshot,
          code_ref: versionCodeRef.trim(),
          change_log: versionChangeLog.trim(),
        }),
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        throw new Error(detail.detail || `发布版本失败: ${res.status}`);
      }
      const item = await res.json();
      setVersionChangeLog("");
      setSelectedVersionId(item.strategy_version_id);
      await loadStrategyDetails(selectedStrategyId);
    } catch (err) {
      setError(err.message || "发布版本失败");
    }
  };

  const createRunMeta = async (event) => {
    event.preventDefault();
    if (!selectedStrategyId || !selectedVersionId) return;
    setError("");
    setRunCreating(true);
    try {
      const res = await apiFetch("/backtests", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          strategy_id: selectedStrategyId,
          strategy_version_id: selectedVersionId,
          start_date: runStartDate.replaceAll("-", ""),
          end_date: runEndDate.replaceAll("-", ""),
          run_type: runType,
          initial_capital: 1000000,
        }),
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        throw new Error(detail.detail || `创建回测失败: ${res.status}`);
      }
      const item = await res.json();
      await loadStrategyDetails(selectedStrategyId);
      router.push(`/backtests/${item.run_id}`);
    } catch (err) {
      setError(err.message || "创建回测失败");
    } finally {
      setRunCreating(false);
    }
  };

  const toggleRunSelect = (runId, checked) => {
    setSelectedRunIds((prev) => {
      if (checked) {
        if (prev.includes(runId)) return prev;
        if (prev.length >= 5) return prev;
        return [...prev, runId];
      }
      return prev.filter((item) => item !== runId);
    });
  };

  const goCompare = () => {
    if (selectedRunIds.length < 2) return;
    const query = encodeURIComponent(selectedRunIds.join(","));
    router.push(`/backtests/compare?run_ids=${query}`);
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
      await Promise.all([loadStrategyDetails(selectedStrategyId), loadStrategies(page)]);
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
          <p className="eyebrow">Strategy Center</p>
          <h1>策略中心</h1>
          <p className="subtitle">管理策略、版本、历史回测并进行效果对比</p>
        </div>
        <div className="header-actions">
          <button className="primary" onClick={() => loadStrategies(page)} disabled={loading}>
            {loading ? "刷新中..." : "刷新"}
          </button>
        </div>
      </header>

      {error ? <div className="error">{error}</div> : null}

      <section className="panel" style={{ marginBottom: 20 }}>
        <h3 style={{ marginTop: 0 }}>创建策略</h3>
        <form className="form-grid" onSubmit={createStrategy}>
          <label className="field">
            <span>名称</span>
            <input value={newName} onChange={(e) => setNewName(e.target.value)} required />
          </label>
          <label className="field">
            <span>Owner</span>
            <input value={newOwner} onChange={(e) => setNewOwner(e.target.value)} />
          </label>
          <label className="field" style={{ gridColumn: "1 / -1" }}>
            <span>描述</span>
            <input value={newDescription} onChange={(e) => setNewDescription(e.target.value)} />
          </label>
          <div className="form-actions">
            <button className="primary" type="submit" disabled={loading || !newName.trim()}>
              新建策略
            </button>
          </div>
        </form>
      </section>

      <section className="table-wrap" style={{ marginBottom: 24 }}>
        <table>
          <thead>
            <tr>
              <th>策略ID</th>
              <th>名称</th>
              <th>状态</th>
              <th>最近Run</th>
              <th>累计收益</th>
              <th>更新时间</th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 ? (
              <tr>
                <td colSpan={6} className="empty">
                  暂无策略
                </td>
              </tr>
            ) : (
              items.map((item) => (
                <tr
                  key={item.strategy_id}
                  onClick={() => setSelectedStrategyId(item.strategy_id)}
                  style={{
                    cursor: "pointer",
                    background:
                      selectedStrategyId === item.strategy_id
                        ? "rgba(226,59,46,0.08)"
                        : "transparent",
                  }}
                >
                  <td>{item.strategy_id}</td>
                  <td>{item.name}</td>
                  <td>{item.status || "-"}</td>
                  <td>{item.latest_run_id || "-"}</td>
                  <td>{formatPct(item?.latest_summary?.total_return)}</td>
                  <td>{formatDateTime(item.updated_at)}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </section>

      <div className="pagination" style={{ marginBottom: 24 }}>
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

      {selectedStrategyId ? (
        <>
          <section className="panel" style={{ marginBottom: 20 }}>
            <h3 style={{ marginTop: 0 }}>发布版本（策略: {selectedStrategyId}）</h3>
            <form onSubmit={createVersion}>
              <div className="form-grid">
                <label className="field">
                  <span>Code Ref</span>
                  <input value={versionCodeRef} onChange={(e) => setVersionCodeRef(e.target.value)} />
                </label>
                <label className="field">
                  <span>变更说明</span>
                  <input value={versionChangeLog} onChange={(e) => setVersionChangeLog(e.target.value)} />
                </label>
                <label className="field" style={{ gridColumn: "1 / -1" }}>
                  <span>params_snapshot(JSON)</span>
                  <textarea
                    rows={8}
                    value={paramsText}
                    onChange={(e) => setParamsText(e.target.value)}
                    style={{ width: "100%", borderRadius: 10, border: "1px solid var(--border-light)", padding: 10 }}
                  />
                </label>
                <div className="form-actions">
                  <button className="primary" type="submit">
                    发布版本
                  </button>
                </div>
              </div>
            </form>
          </section>

          <section className="panel" style={{ marginBottom: 20 }}>
            <h3 style={{ marginTop: 0 }}>创建回测Run</h3>
            <form className="form-grid" onSubmit={createRunMeta}>
              <label className="field">
                <span>版本</span>
                <select value={selectedVersionId} onChange={(e) => setSelectedVersionId(e.target.value)} required>
                  <option value="">请选择版本</option>
                  {versions.map((item) => (
                    <option key={item.strategy_version_id} value={item.strategy_version_id}>
                      {item.version} ({item.strategy_version_id})
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>Run Type</span>
                <select value={runType} onChange={(e) => setRunType(e.target.value)}>
                  <option value="range">range</option>
                  <option value="full_history">full_history</option>
                </select>
              </label>
              <label className="field">
                <span>开始日期</span>
                <input value={runStartDate} onChange={(e) => setRunStartDate(e.target.value)} required />
              </label>
              <label className="field">
                <span>结束日期</span>
                <input value={runEndDate} onChange={(e) => setRunEndDate(e.target.value)} required />
              </label>
              <div className="form-actions">
                <button className="primary" type="submit" disabled={runCreating || !selectedVersionId}>
                  {runCreating ? "创建中..." : "创建回测元信息"}
                </button>
              </div>
            </form>
          </section>

          <section className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>对比</th>
                  <th>Run ID</th>
                  <th>版本</th>
                  <th>状态</th>
                  <th>区间</th>
                  <th>累计收益</th>
                  <th>创建时间</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {runs.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="empty">
                      暂无回测记录
                    </td>
                  </tr>
                ) : (
                  runs.map((item) => (
                    <tr key={item.run_id}>
                      <td>
                        <input
                          type="checkbox"
                          checked={selectedRunIds.includes(item.run_id)}
                          onChange={(e) => toggleRunSelect(item.run_id, e.target.checked)}
                        />
                      </td>
                      <td>
                        <a className="link-button" href={`/freedom/backtests/${item.run_id}`}>
                          {item.run_id}
                        </a>
                      </td>
                      <td>{item.strategy_version_id}</td>
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
                            disabled={deletingRunId === item.run_id || item.status === "running"}
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

          <div style={{ marginTop: 16, display: "flex", gap: 12 }}>
            <button
              className="primary"
              type="button"
              disabled={selectedRunIds.length < 2}
              onClick={goCompare}
            >
              对比已选 Run（{selectedRunIds.length}/5）
            </button>
          </div>
        </>
      ) : null}

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
