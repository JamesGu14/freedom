import { useEffect, useMemo, useState } from "react";
import { apiFetch } from "../../lib/api";

const formatDate = (value) => {
  const text = String(value || "").replace(/-/g, "");
  if (text.length !== 8) return value || "-";
  return `${text.slice(0, 4)}-${text.slice(4, 6)}-${text.slice(6, 8)}`;
};

const formatNum = (value, digits = 2) => {
  if (value === null || value === undefined || value === "") return "-";
  const num = Number(value);
  if (Number.isNaN(num)) return String(value);
  return num.toFixed(digits);
};

const formatPct = (value) => {
  if (value === null || value === undefined || value === "") return "-";
  const num = Number(value);
  if (Number.isNaN(num)) return String(value);
  const prefix = num > 0 ? "+" : "";
  return `${prefix}${num.toFixed(2)}%`;
};

const TableSection = ({ title, rows, columns }) => (
  <section className="panel">
    <h3>{title}</h3>
    {Array.isArray(rows) && rows.length > 0 ? (
      <div className="table-wrap research-table-wrap">
        <table>
          <thead>
            <tr>
              {columns.map((column) => (
                <th key={column.key}>{column.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, idx) => (
              <tr key={`${title}-${idx}`}>
                {columns.map((column) => (
                  <td key={column.key}>
                    {column.render ? column.render(row[column.key], row) : row[column.key] ?? "-"}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    ) : (
      <div className="empty">暂无数据</div>
    )}
  </section>
);

export default function MarketResearchPage() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [indexes, setIndexes] = useState(null);
  const [indexDetail, setIndexDetail] = useState(null);
  const [sectors, setSectors] = useState(null);
  const [hsgtFlow, setHsgtFlow] = useState(null);
  const [selectedIndex, setSelectedIndex] = useState("");

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      setError("");
      try {
        const responses = await Promise.all([
          apiFetch("/research/market/indexes"),
          apiFetch("/research/market/sectors"),
          apiFetch("/research/market/hsgt-flow"),
        ]);
        const payloads = await Promise.all(
          responses.map(async (res) => {
            if (!res.ok) {
              const detail = await res.json().catch(() => ({}));
              throw new Error(detail.detail || `加载失败: ${res.status}`);
            }
            return res.json();
          })
        );
        if (cancelled) return;
        setIndexes(payloads[0]);
        setSectors(payloads[1]);
        setHsgtFlow(payloads[2]);
        const defaultCode = payloads[0]?.tracked_indexes?.[0]?.ts_code || "";
        setSelectedIndex(defaultCode);
      } catch (err) {
        if (!cancelled) setError(err.message || "加载失败");
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!selectedIndex) return;
    let cancelled = false;
    const loadDetail = async () => {
      try {
        const res = await apiFetch(`/research/market/indexes/${encodeURIComponent(selectedIndex)}`);
        if (!res.ok) {
          const detail = await res.json().catch(() => ({}));
          throw new Error(detail.detail || `加载失败: ${res.status}`);
        }
        const data = await res.json();
        if (!cancelled) setIndexDetail(data);
      } catch (err) {
        if (!cancelled) setError(err.message || "加载失败");
      }
    };
    loadDetail();
    return () => {
      cancelled = true;
    };
  }, [selectedIndex]);

  const selectedIndexName = useMemo(() => indexDetail?.basic?.name || selectedIndex, [indexDetail, selectedIndex]);

  return (
    <main className="page">
      <header className="header">
        <div>
          <p className="eyebrow">Research</p>
          <h1>市场研究</h1>
          <p className="subtitle">围绕核心指数、行业强弱和沪深港通资金流构建市场研究视图。</p>
        </div>
      </header>

      {error ? <div className="error">{error}</div> : null}
      {loading ? <div className="panel"><p className="subtitle">加载中...</p></div> : null}

      <section className="panel">
        <div className="panel-title-row">
          <h2>核心指数快照</h2>
          <span className="badge">最近日期 {indexes?.available_dates?.[0] ? formatDate(indexes.available_dates[0]) : "-"}</span>
        </div>
        <div className="research-card-grid">
          {(indexes?.latest_snapshot || []).map((item) => (
            <button
              key={item.ts_code}
              type="button"
              className={`research-index-card${selectedIndex === item.ts_code ? " research-index-card--active" : ""}`}
              onClick={() => setSelectedIndex(item.ts_code)}
            >
              <strong>{item.name || item.ts_code}</strong>
              <span>{item.ts_code}</span>
              <span>收盘 {formatNum(item.close)}</span>
              <span>{formatPct(item.pct_chg || item.pct_change)}</span>
            </button>
          ))}
        </div>
      </section>

      <section className="panel">
        <div className="panel-title-row">
          <h2>指数详情</h2>
          <span className="badge">{selectedIndexName || "-"}</span>
        </div>
        <div className="filters">
          <label className="field">
            <span>指数</span>
            <select value={selectedIndex} onChange={(event) => setSelectedIndex(event.target.value)}>
              {(indexes?.tracked_indexes || []).map((item) => (
                <option key={item.ts_code} value={item.ts_code}>
                  {item.name || item.ts_code}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="research-key-value-grid">
          <div className="research-key-value-item">
            <span>市场</span>
            <strong>{indexDetail?.basic?.market || "-"}</strong>
          </div>
          <div className="research-key-value-item">
            <span>分类</span>
            <strong>{indexDetail?.basic?.category || "-"}</strong>
          </div>
          <div className="research-key-value-item">
            <span>样本数</span>
            <strong>{indexDetail?.daily?.length || 0}</strong>
          </div>
          <div className="research-key-value-item">
            <span>因子样本数</span>
            <strong>{indexDetail?.factors?.length || 0}</strong>
          </div>
        </div>
      </section>

      <TableSection
        title="指数日线"
        rows={indexDetail?.daily}
        columns={[
          { key: "trade_date", label: "交易日", render: formatDate },
          { key: "close", label: "收盘", render: formatNum },
          { key: "pct_chg", label: "涨跌幅", render: formatPct },
          { key: "vol", label: "成交量", render: formatNum },
          { key: "amount", label: "成交额", render: formatNum },
        ]}
      />

      <TableSection
        title="大盘指数每日指标"
        rows={indexDetail?.dailybasic}
        columns={[
          { key: "trade_date", label: "交易日", render: formatDate },
          { key: "pe", label: "PE", render: formatNum },
          { key: "pb", label: "PB", render: formatNum },
          { key: "total_mv", label: "总市值", render: formatNum },
          { key: "turnover_rate", label: "换手率", render: formatNum },
        ]}
      />

      <TableSection
        title="指数扩展因子"
        rows={indexDetail?.factors}
        columns={[
          { key: "trade_date", label: "交易日", render: formatDate },
          { key: "pct_change", label: "涨跌幅", render: formatPct },
          { key: "simple_return", label: "简单收益", render: formatNum },
          { key: "macd_bfq", label: "MACD", render: formatNum },
          { key: "rsi_bfq_6", label: "RSI6", render: formatNum },
        ]}
      />

      <TableSection
        title="申万行业快照"
        rows={sectors?.shenwan}
        columns={[
          { key: "trade_date", label: "交易日", render: formatDate },
          { key: "name", label: "行业" },
          { key: "pct_change", label: "涨跌幅", render: formatPct },
          { key: "rank", label: "排名" },
        ]}
      />

      <TableSection
        title="中信行业快照"
        rows={sectors?.citic}
        columns={[
          { key: "trade_date", label: "交易日", render: formatDate },
          { key: "name", label: "行业" },
          { key: "pct_change", label: "涨跌幅", render: formatPct },
          { key: "rank", label: "排名" },
        ]}
      />

      <TableSection
        title="沪深港通资金流"
        rows={hsgtFlow?.items}
        columns={[
          { key: "trade_date", label: "交易日", render: formatDate },
          { key: "north_money", label: "北向资金", render: formatNum },
          { key: "south_money", label: "南向资金", render: formatNum },
          { key: "hgt", label: "沪股通", render: formatNum },
          { key: "sgt", label: "深股通", render: formatNum },
        ]}
      />
    </main>
  );
}
