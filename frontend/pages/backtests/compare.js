import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/router";
import { apiFetch } from "../../lib/api";

const formatPct = (value) => {
  if (value === null || value === undefined || value === "") return "-";
  const num = Number(value);
  if (Number.isNaN(num)) return "-";
  const prefix = num > 0 ? "+" : "";
  return `${prefix}${(num * 100).toFixed(2)}%`;
};

const formatDate = (value) => {
  const text = String(value || "");
  if (text.length !== 8) return text || "-";
  return `${text.slice(0, 4)}-${text.slice(4, 6)}-${text.slice(6, 8)}`;
};

const buildCompareChartOption = (items = []) => {
  const dateSet = new Set();
  items.forEach((item) => {
    (item.nav_series || []).forEach((row) => dateSet.add(String(row.trade_date)));
  });
  const dates = Array.from(dateSet).sort();
  const series = items.map((item, idx) => {
    const map = new Map((item.nav_series || []).map((row) => [String(row.trade_date), Number(row.nav || 0)]));
    const colorSet = ["#e23b2e", "#0ea5e9", "#16a34a", "#a855f7", "#f59e0b"];
    return {
      name: item.run_id,
      type: "line",
      showSymbol: false,
      smooth: true,
      lineStyle: { width: 2, color: colorSet[idx % colorSet.length] },
      data: dates.map((date) => map.get(date) ?? null),
    };
  });
  return {
    tooltip: { trigger: "axis" },
    legend: { top: 8, data: items.map((item) => item.run_id) },
    grid: { left: 56, right: 24, top: 40, bottom: 36 },
    xAxis: { type: "category", data: dates.map((item) => formatDate(item)) },
    yAxis: { type: "value", name: "净值" },
    series,
  };
};

export default function BacktestComparePage() {
  const router = useRouter();
  const chartRef = useRef(null);
  const chartInstanceRef = useRef(null);

  const [runIdsInput, setRunIdsInput] = useState("");
  const [items, setItems] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const years = useMemo(() => {
    const set = new Set();
    items.forEach((item) => {
      const annual = item?.summary_metrics?.annual_returns || {};
      Object.keys(annual).forEach((year) => set.add(year));
    });
    return Array.from(set).sort();
  }, [items]);

  const loadData = async (runIds) => {
    if (!runIds.length) return;
    setLoading(true);
    setError("");
    try {
      const res = await apiFetch("/backtests/compare", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ run_ids: runIds }),
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        throw new Error(detail.detail || `加载失败: ${res.status}`);
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
    const raw = String(router.query.run_ids || "");
    if (!raw) return;
    const runIds = raw
      .split(",")
      .map((item) => item.trim())
      .filter((item) => item);
    if (!runIds.length) return;
    setRunIdsInput(runIds.join(","));
    loadData(runIds.slice(0, 5));
  }, [router.query.run_ids]);

  useEffect(() => {
    if (!chartRef.current || items.length === 0) return;
    let disposed = false;
    import("echarts").then((echarts) => {
      if (disposed || !chartRef.current) return;
      if (!chartInstanceRef.current) {
        chartInstanceRef.current = echarts.init(chartRef.current);
      }
      chartInstanceRef.current.setOption(buildCompareChartOption(items), true);
    });
    const handleResize = () => chartInstanceRef.current?.resize();
    window.addEventListener("resize", handleResize);
    return () => {
      disposed = true;
      window.removeEventListener("resize", handleResize);
    };
  }, [items]);

  useEffect(() => () => chartInstanceRef.current?.dispose(), []);

  const handleSubmit = async (event) => {
    event.preventDefault();
    const runIds = runIdsInput
      .split(",")
      .map((item) => item.trim())
      .filter((item) => item);
    if (runIds.length < 2 || runIds.length > 5) {
      setError("run_ids 数量需在 2 到 5 之间");
      return;
    }
    router.replace(`/backtests/compare?run_ids=${encodeURIComponent(runIds.join(","))}`, undefined, {
      shallow: true,
    });
    await loadData(runIds);
  };

  return (
    <main className="page">
      <header className="header">
        <div>
          <p className="eyebrow">Backtests Compare</p>
          <h1>回测对比</h1>
          <p className="subtitle">最多选择 5 个 run 进行净值与年度指标对比</p>
        </div>
        <div className="header-actions">
          <Link className="primary" href="/strategies">
            返回策略页
          </Link>
        </div>
      </header>

      <form className="filters" onSubmit={handleSubmit}>
        <label className="field" style={{ gridColumn: "1 / -1" }}>
          <span>Run IDs（逗号分隔）</span>
          <input
            value={runIdsInput}
            onChange={(e) => setRunIdsInput(e.target.value)}
            placeholder="run1,run2,run3"
          />
        </label>
        <div className="form-actions">
          <button className="primary" type="submit" disabled={loading}>
            {loading ? "加载中..." : "开始对比"}
          </button>
        </div>
      </form>

      {error ? <div className="error">{error}</div> : null}

      <section className="panel" style={{ marginBottom: 20 }}>
        <h3 style={{ marginTop: 0 }}>净值曲线对比</h3>
        <div
          ref={chartRef}
          style={{
            width: "100%",
            height: 420,
            border: "1px solid var(--border-light)",
            borderRadius: 12,
          }}
        />
      </section>

      <section className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Run ID</th>
              <th>累计收益</th>
              {years.map((year) => (
                <th key={`ret-${year}`}>{year} 年化</th>
              ))}
              {years.map((year) => (
                <th key={`dd-${year}`}>{year} 回撤</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {items.length === 0 ? (
              <tr>
                <td colSpan={2 + years.length * 2} className="empty">
                  暂无对比数据
                </td>
              </tr>
            ) : (
              items.map((item) => {
                const annualReturns = item?.summary_metrics?.annual_returns || {};
                const annualDrawdowns = item?.summary_metrics?.annual_max_drawdowns || {};
                return (
                  <tr key={item.run_id}>
                    <td>
                      <Link className="link-button" href={`/backtests/${item.run_id}`}>
                        {item.run_id}
                      </Link>
                    </td>
                    <td>{formatPct(item?.summary_metrics?.total_return)}</td>
                    {years.map((year) => (
                      <td key={`${item.run_id}-ret-${year}`}>{formatPct(annualReturns[year])}</td>
                    ))}
                    {years.map((year) => (
                      <td key={`${item.run_id}-dd-${year}`}>{formatPct(annualDrawdowns[year])}</td>
                    ))}
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </section>
    </main>
  );
}

