import { useEffect, useMemo, useRef, useState } from "react";
import { apiFetch } from "../lib/api";

const toInputDate = (value) => {
  const text = String(value || "").replace(/-/g, "");
  if (text.length !== 8) return "";
  return `${text.slice(0, 4)}-${text.slice(4, 6)}-${text.slice(6, 8)}`;
};

const fromInputDate = (value) => String(value || "").replace(/-/g, "");

const todayInput = () => {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
};

const toNum = (value) => {
  const text = String(value ?? "").trim();
  if (!text) return null;
  const num = Number(text);
  return Number.isFinite(num) ? num : null;
};

const formatMoney = (value) => {
  const num = Number(value);
  if (!Number.isFinite(num)) return "-";
  return num.toFixed(2);
};

const formatPercent = (value) => {
  const num = Number(value);
  if (!Number.isFinite(num)) return "-";
  return `${(num * 100).toFixed(2)}%`;
};

const normalizeTsCodeInput = (value) => {
  const text = String(value || "").trim().toUpperCase();
  if (!text) return "";
  if (text.includes(".")) return text;
  if (!/^\d{6}$/.test(text)) return text;
  if (/^(600|601|603|605|688|689|900)/.test(text)) return `${text}.SH`;
  if (/^(000|001|002|003|200|300|301)/.test(text)) return `${text}.SZ`;
  if (/^[48]/.test(text)) return `${text}.BJ`;
  return text;
};

const calcRowEstimatedPrice = (row) => {
  const costPrice = toNum(row?.cost_price);
  if (costPrice !== null && costPrice > 0) {
    return costPrice;
  }
  const currentPrice = toNum(row?.current_price);
  if (currentPrice !== null && currentPrice > 0) {
    return currentPrice;
  }
  return null;
};

const calcRowEstimatedMarketValue = (row) => {
  const quantity = toNum(row?.quantity);
  const price = calcRowEstimatedPrice(row);
  if (quantity !== null && quantity > 0 && price !== null && price > 0) {
    return quantity * price;
  }
  const marketValue = toNum(row?.market_value);
  if (marketValue !== null && marketValue >= 0) {
    return marketValue;
  }
  return 0;
};

const calcRowAutoCurrentPrice = (row) => {
  const currentPrice = toNum(row?.current_price);
  if (currentPrice !== null && currentPrice > 0) {
    return currentPrice;
  }
  return null;
};

const calcRowAutoMarketValue = (row) => {
  const quantity = toNum(row?.quantity);
  const currentPrice = calcRowAutoCurrentPrice(row);
  if (quantity !== null && quantity > 0 && currentPrice !== null && currentPrice > 0) {
    return quantity * currentPrice;
  }
  const marketValue = toNum(row?.market_value);
  if (marketValue !== null && marketValue >= 0) {
    return marketValue;
  }
  return null;
};

const makeEmptyPosition = (rowKey = "") => ({
  row_key: rowKey,
  ts_code: "",
  quantity: "",
  cost_price: "",
  entry_date: "",
  stock_name: "",
  industry: "",
  current_price: "",
  market_value: "",
});

const normalizePositionRow = (item, rowKey = "") => ({
  row_key: rowKey,
  ts_code: String(item?.ts_code || "").toUpperCase(),
  quantity: item?.quantity ?? item?.shares ?? "",
  cost_price: item?.cost_price ?? item?.avg_cost ?? "",
  entry_date: toInputDate(item?.entry_date || ""),
  stock_name: String(item?.stock_name || item?.name || ""),
  industry: String(item?.industry || ""),
  current_price: item?.current_price ?? item?.market_price ?? "",
  market_value: item?.market_value ?? item?.position_value ?? "",
});

export default function AgentFreedomPage() {
  const rowSeqRef = useRef(0);
  const [accountId, setAccountId] = useState("main");
  const [tradeDate, setTradeDate] = useState(todayInput);
  const [accountForm, setAccountForm] = useState({
    account_name: "Main Account",
    total_equity: "",
    cash: "",
  });
  const [positions, setPositions] = useState([]);
  const [replaceAll, setReplaceAll] = useState(false);

  const [summary, setSummary] = useState(null);
  const [latestReport, setLatestReport] = useState(null);
  const [runResult, setRunResult] = useState(null);

  const [loadingAccount, setLoadingAccount] = useState(false);
  const [loadingPositions, setLoadingPositions] = useState(false);
  const [savingAccount, setSavingAccount] = useState(false);
  const [savingPositions, setSavingPositions] = useState(false);
  const [running, setRunning] = useState(false);

  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const nextRowKey = () => {
    rowSeqRef.current += 1;
    return `row-${Date.now()}-${rowSeqRef.current}`;
  };

  const normalizedAccountId = useMemo(() => {
    const text = String(accountId || "").trim();
    return text || "main";
  }, [accountId]);

  const positionCount = useMemo(() => positions.filter((item) => String(item.ts_code || "").trim()).length, [positions]);
  const estimatedMarketValue = useMemo(() => positions.reduce((sum, row) => sum + calcRowEstimatedMarketValue(row), 0), [positions]);
  const totalEquityInput = toNum(accountForm.total_equity);
  const persistedCash = toNum(summary?.cash);
  const linkedCash = toNum(accountForm.cash) ?? persistedCash;
  const estimatedCash = totalEquityInput === null ? null : totalEquityInput - estimatedMarketValue;
  const linkedTotalEquity = linkedCash === null ? null : estimatedMarketValue + linkedCash;
  const linkedGrossExposure = linkedTotalEquity && linkedTotalEquity > 0 ? estimatedMarketValue / linkedTotalEquity : null;

  const clearHint = () => {
    setError("");
    setNotice("");
  };

  const loadAccount = async (targetAccountId = normalizedAccountId) => {
    setLoadingAccount(true);
    try {
      const accountKey = String(targetAccountId || "").trim() || "main";
      const res = await apiFetch(`/agent-freedom/portfolio/accounts/${encodeURIComponent(accountKey)}`);
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        throw new Error(detail.detail || `账户加载失败: ${res.status}`);
      }
      const data = await res.json();
      const item = data.item;
      if (!item) {
        setAccountForm({
          account_name: accountKey,
          total_equity: "",
          cash: "",
        });
        setSummary(null);
        return;
      }
      setAccountForm({
        account_name: String(item.account_name || accountKey),
        total_equity: item.total_equity ?? "",
        cash: item.cash ?? "",
      });
      setSummary(item.summary || null);
    } finally {
      setLoadingAccount(false);
    }
  };

  const loadPositions = async (targetAccountId = normalizedAccountId) => {
    setLoadingPositions(true);
    try {
      const accountKey = String(targetAccountId || "").trim() || "main";
      const res = await apiFetch(`/agent-freedom/portfolio/positions/${encodeURIComponent(accountKey)}`);
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        throw new Error(detail.detail || `持仓加载失败: ${res.status}`);
      }
      const data = await res.json();
      const rows = (data.items || []).map((item) => normalizePositionRow(item, nextRowKey()));
      setPositions(rows);
      if (data.summary) {
        setSummary(data.summary);
      }
    } finally {
      setLoadingPositions(false);
    }
  };

  const loadLatestReport = async (targetDate = tradeDate) => {
    const ymd = fromInputDate(targetDate);
    if (!ymd) {
      setLatestReport(null);
      return;
    }
    const params = new URLSearchParams();
    params.set("trade_date", ymd);
    const res = await apiFetch(`/agent-freedom/report/latest?${params.toString()}`);
    if (!res.ok) {
      return;
    }
    const data = await res.json();
    setLatestReport(data.item || null);
  };

  const refreshAll = async (targetAccountId = normalizedAccountId) => {
    clearHint();
    try {
      await Promise.all([loadAccount(targetAccountId), loadPositions(targetAccountId), loadLatestReport(tradeDate)]);
      setNotice(`已加载账户 ${String(targetAccountId || "").trim() || "main"}`);
    } catch (err) {
      setError(err.message || "加载失败");
    }
  };

  useEffect(() => {
    refreshAll("main");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const saveAccountValues = async ({ totalEquity, cash, successNotice }) => {
    setSavingAccount(true);
    try {
      const res = await apiFetch(`/agent-freedom/portfolio/accounts/${encodeURIComponent(normalizedAccountId)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          account_name: String(accountForm.account_name || normalizedAccountId).trim() || normalizedAccountId,
          total_equity: totalEquity,
          cash,
          metadata: {},
        }),
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        throw new Error(detail.detail || `账户保存失败: ${res.status}`);
      }
      const data = await res.json();
      const nextSummary = data.item?.summary || null;
      setSummary(nextSummary);
      setAccountForm((prev) => ({
        ...prev,
        total_equity: totalEquity.toFixed(2),
        cash: cash.toFixed(2),
      }));
      setNotice(successNotice || `账户 ${normalizedAccountId} 已保存`);
      return true;
    } catch (err) {
      setError(err.message || "账户保存失败");
      return false;
    } finally {
      setSavingAccount(false);
    }
  };

  const onSaveAccount = async (event) => {
    event.preventDefault();
    clearHint();
    const totalEquity = toNum(accountForm.total_equity);
    let cash = toNum(accountForm.cash);
    if (totalEquity === null || totalEquity < 0) {
      setError("请输入有效的目标总资金");
      return;
    }
    if (cash === null) {
      cash = totalEquity - estimatedMarketValue;
    }
    if (cash === null || cash < 0) {
      setError("现金无效：请填写现金，或先保存持仓后自动计算现金");
      return;
    }
    await saveAccountValues({
      totalEquity,
      cash,
      successNotice: `账户 ${normalizedAccountId} 已保存`,
    });
  };

  const onSavePositions = async (event) => {
    event.preventDefault();
    clearHint();
    if (replaceAll) {
      const confirmed = window.confirm("你已勾选全量替换，保存后将删除当前账户已有持仓，仅保留本次表格内容。确定继续吗？");
      if (!confirmed) {
        setNotice("已取消本次全量替换保存");
        return;
      }
    }
    const payloadPositions = [];
    for (let index = 0; index < positions.length; index += 1) {
      const row = positions[index];
      const tsCode = normalizeTsCodeInput(row.ts_code);
      if (!tsCode) {
        continue;
      }
      const quantity = toNum(row.quantity);
      const costPrice = toNum(row.cost_price);
      if (quantity === null || quantity <= 0) {
        setError(`第 ${index + 1} 行数量无效，请填写大于 0 的数量`);
        return;
      }
      if (costPrice === null || costPrice <= 0) {
        setError(`第 ${index + 1} 行成本价无效，请填写大于 0 的成本价`);
        return;
      }
      const item = {
        ts_code: tsCode,
        quantity,
        cost_price: costPrice,
      };
      const entryDate = fromInputDate(row.entry_date);
      if (entryDate) item.entry_date = entryDate;
      payloadPositions.push(item);
    }

    setSavingPositions(true);
    try {
      const res = await apiFetch(`/agent-freedom/portfolio/positions/${encodeURIComponent(normalizedAccountId)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          positions: payloadPositions,
          snapshot_trade_date: fromInputDate(tradeDate),
          replace_all: replaceAll,
        }),
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        throw new Error(detail.detail || `持仓保存失败: ${res.status}`);
      }
      const data = await res.json();
      setPositions((data.items || []).map((item) => normalizePositionRow(item, nextRowKey())));
      setSummary(data.summary || null);
      setNotice(`持仓已保存，写入 ${data.upserted || 0} 条`);
    } catch (err) {
      setError(err.message || "持仓保存失败");
    } finally {
      setSavingPositions(false);
    }
  };

  const onAutoFillCash = async () => {
    clearHint();
    const totalEquity = toNum(accountForm.total_equity);
    if (totalEquity === null || totalEquity < 0) {
      setError("请先填写有效的目标总资金，再自动计算现金");
      return;
    }
    const nextCash = totalEquity - estimatedMarketValue;
    if (nextCash < 0) {
      setError("当前持仓总市值大于总资金，无法得到非负现金，请先调整数据");
      return;
    }
    setAccountForm((prev) => ({ ...prev, cash: nextCash.toFixed(2) }));
    await saveAccountValues({
      totalEquity,
      cash: nextCash,
      successNotice: "已按当前持仓回填现金并保存到账户",
    });
  };

  const onRunDaily = async () => {
    clearHint();
    const ymd = fromInputDate(tradeDate);
    if (!ymd) {
      setError("请先选择有效的交易日期");
      return;
    }
    setRunning(true);
    try {
      const params = new URLSearchParams();
      params.set("trade_date", ymd);
      params.set("account_id", normalizedAccountId);
      const res = await apiFetch(`/agent-freedom/run?${params.toString()}`, {
        method: "POST",
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        throw new Error(detail.detail || `运行失败: ${res.status}`);
      }
      const data = await res.json();
      setRunResult(data);
      await loadLatestReport(tradeDate);
      setNotice(`运行完成，状态: ${data.status || "-"}`);
    } catch (err) {
      setError(err.message || "运行失败");
    } finally {
      setRunning(false);
    }
  };

  const updatePositionField = (index, field, value) => {
    setPositions((prev) => prev.map((item, idx) => (idx === index ? { ...item, [field]: value } : item)));
  };

  const normalizePositionTsCodeField = (index) => {
    setPositions((prev) =>
      prev.map((item, idx) => {
        if (idx !== index) return item;
        return {
          ...item,
          ts_code: normalizeTsCodeInput(item.ts_code),
        };
      })
    );
  };

  const removePosition = (index) => {
    setPositions((prev) => prev.filter((_, idx) => idx !== index));
  };

  return (
    <main className="page">
      <header className="header">
        <div>
          <p className="eyebrow">Agent Freedom</p>
          <h1>财神爷账户管理</h1>
          <p className="subtitle">录入账户资金与持仓，驱动风控规则生效</p>
        </div>
      </header>

      <section className="filters">
        <label className="field">
          <span>账户 ID</span>
          <input
            type="text"
            value={accountId}
            onChange={(event) => setAccountId(event.target.value)}
            placeholder="main"
          />
        </label>
        <label className="field">
          <span>交易日期</span>
          <input type="date" value={tradeDate} onChange={(event) => setTradeDate(event.target.value)} />
        </label>
        <div className="af-toolbar-actions">
          <button
            className="link-button"
            type="button"
            onClick={() => refreshAll(normalizedAccountId)}
            disabled={loadingAccount || loadingPositions}
          >
            刷新账户
          </button>
          <button className="primary" type="button" onClick={onRunDaily} disabled={running}>
            {running ? "运行中..." : "运行当日任务"}
          </button>
        </div>
      </section>

      {error ? <div className="error">{error}</div> : null}
      {notice ? <div className="notice">{notice}</div> : null}

      <section className="panel form-panel">
        <div className="panel-title-row">
          <h2>账户资金</h2>
          {loadingAccount ? <span className="muted-text">加载中...</span> : null}
        </div>
        <form className="form-grid" onSubmit={onSaveAccount}>
          <label className="field">
            <span>账户名称</span>
            <input
              type="text"
              value={accountForm.account_name}
              onChange={(event) => setAccountForm((prev) => ({ ...prev, account_name: event.target.value }))}
            />
          </label>
          <label className="field">
            <span>目标总资金</span>
            <input
              type="number"
              min="0"
              step="0.01"
              value={accountForm.total_equity}
              onChange={(event) => setAccountForm((prev) => ({ ...prev, total_equity: event.target.value }))}
            />
          </label>
          <label className="field">
            <span>现金</span>
            <input
              type="number"
              min="0"
              step="0.01"
              value={accountForm.cash}
              onChange={(event) => setAccountForm((prev) => ({ ...prev, cash: event.target.value }))}
            />
          </label>
          <div className="form-actions">
            <button className="link-button" type="button" onClick={onAutoFillCash} disabled={savingAccount}>
              按持仓回填现金
            </button>
            <button className="primary" type="submit" disabled={savingAccount}>
              {savingAccount ? "保存中..." : "保存账户"}
            </button>
          </div>
        </form>
        <p className="muted-text">
          联动估算（成本口径）：总市值 {formatMoney(estimatedMarketValue)}；现金 {linkedCash === null ? "-" : formatMoney(linkedCash)}；总资金{" "}
          {linkedTotalEquity === null ? "-" : formatMoney(linkedTotalEquity)}；总暴露 {formatPercent(linkedGrossExposure)}；按目标总资金反推现金{" "}
          {estimatedCash === null ? "-" : formatMoney(estimatedCash)}
        </p>
        {summary || positions.length > 0 || String(accountForm.total_equity || "").trim() ? (
          <div className="af-summary-grid">
            <div className="kpi-tile">
              <div className="kpi-tile__label">持仓数</div>
              <div className="kpi-tile__value">{positionCount}</div>
            </div>
            <div className="kpi-tile">
              <div className="kpi-tile__label">总市值</div>
              <div className="kpi-tile__value">{formatMoney(estimatedMarketValue)}</div>
            </div>
            <div className="kpi-tile">
              <div className="kpi-tile__label">总资金</div>
              <div className="kpi-tile__value">{linkedTotalEquity === null ? "-" : formatMoney(linkedTotalEquity)}</div>
            </div>
            <div className="kpi-tile">
              <div className="kpi-tile__label">总暴露</div>
              <div className="kpi-tile__value">{formatPercent(linkedGrossExposure)}</div>
            </div>
          </div>
        ) : null}
      </section>

      <section className="panel form-panel">
        <div className="panel-title-row">
          <h2>持仓录入</h2>
          <div className="panel-title-actions">
            <button className="link-button" type="button" onClick={() => setPositions((prev) => [...prev, makeEmptyPosition(nextRowKey())])}>
              新增一行
            </button>
            <span className="muted-text">当前 {positionCount} 条</span>
          </div>
        </div>
        <p className="muted-text">仅需录入 TS_CODE、数量、成本价（建仓日可选）；支持输入 6 位代码（如 000830）自动补全后缀，名称/行业/现价/市值自动补全。</p>

        <form onSubmit={onSavePositions}>
          <div className="table-wrap af-table-wrap">
            <table>
              <thead>
                <tr>
                  <th>TS_CODE</th>
                  <th>数量</th>
                  <th>成本价</th>
                  <th>建仓日</th>
                  <th>名称(自动)</th>
                  <th>行业(自动)</th>
                  <th>现价(自动)</th>
                  <th>市值(自动)</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {positions.length === 0 ? (
                  <tr>
                    <td colSpan="9" className="empty">
                      暂无持仓，请先新增一行
                    </td>
                  </tr>
                ) : (
                  positions.map((row, index) => {
                    const displayPrice = calcRowAutoCurrentPrice(row);
                    const displayMarketValue = calcRowAutoMarketValue(row);
                    return (
                    <tr key={row.row_key || `row-${index}`}>
                      <td>
                        <input
                          className="af-table-input"
                          value={row.ts_code}
                          onChange={(event) => updatePositionField(index, "ts_code", event.target.value.toUpperCase())}
                          onBlur={() => normalizePositionTsCodeField(index)}
                          placeholder="000001.SZ"
                        />
                      </td>
                      <td>
                        <input
                          className="af-table-input"
                          type="number"
                          min="0"
                          step="1"
                          value={row.quantity}
                          onChange={(event) => updatePositionField(index, "quantity", event.target.value)}
                          placeholder="0"
                        />
                      </td>
                      <td>
                        <input
                          className="af-table-input"
                          type="number"
                          min="0"
                          step="0.01"
                          value={row.cost_price}
                          onChange={(event) => updatePositionField(index, "cost_price", event.target.value)}
                          placeholder="0"
                        />
                      </td>
                      <td>
                        <input
                          className="af-table-input"
                          type="date"
                          value={row.entry_date}
                          onChange={(event) => updatePositionField(index, "entry_date", event.target.value)}
                        />
                      </td>
                      <td>
                        <span className="af-readonly-cell">{row.stock_name || "-"}</span>
                      </td>
                      <td>
                        <span className="af-readonly-cell">{row.industry || "-"}</span>
                      </td>
                      <td>
                        <span className="af-readonly-cell">{formatMoney(displayPrice)}</span>
                      </td>
                      <td>
                        <span className="af-readonly-cell">{formatMoney(displayMarketValue)}</span>
                      </td>
                      <td>
                        <button className="danger-button" type="button" onClick={() => removePosition(index)}>
                          删除
                        </button>
                      </td>
                    </tr>
                  );
                  })
                )}
              </tbody>
            </table>
          </div>

          <div className="af-position-actions">
            <label className="field">
              <span>快照日期</span>
              <input type="date" value={tradeDate} onChange={(event) => setTradeDate(event.target.value)} />
            </label>
            <label className="af-inline-check">
              <input type="checkbox" checked={replaceAll} onChange={(event) => setReplaceAll(event.target.checked)} />
              <span>全量替换当前账户持仓</span>
            </label>
            <button className="primary" type="submit" disabled={savingPositions}>
              {savingPositions ? "保存中..." : "保存持仓"}
            </button>
          </div>
        </form>
      </section>

      <section className="panel form-panel">
        <div className="panel-title-row">
          <h2>运行结果</h2>
          <button className="link-button" type="button" onClick={() => loadLatestReport(tradeDate)}>
            刷新报告
          </button>
        </div>
        <div className="af-result-grid">
          <div>
            <h3 className="af-result-title">本次运行</h3>
            <pre className="af-json">{JSON.stringify(runResult || {}, null, 2)}</pre>
          </div>
          <div>
            <h3 className="af-result-title">日报摘要</h3>
            <pre className="af-json">{JSON.stringify(latestReport?.stats || {}, null, 2)}</pre>
          </div>
        </div>
      </section>
    </main>
  );
}
