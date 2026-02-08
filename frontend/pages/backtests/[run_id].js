import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/router";
import { apiFetch } from "../../lib/api";

const BENCHMARK_CODE = "000905.SH";
const BENCHMARK_NAME = "中证500";
const REASON_CODE_LABELS = {
  trend_break: "趋势跌破",
  boll_break: "跌破布林中轨",
  boll_lower_break: "跌破布林下轨",
  kdj_dead_cross: "KDJ死叉",
  confirm_pending: "等待确认",
  stop_loss: "止损触发",
  trail_stop: "回撤止盈",
  max_hold: "持仓超期",
  rotate_out: "调仓换股",
  score_rank: "评分入选",
};

const formatPct = (value) => {
  if (value === null || value === undefined || value === "") return "-";
  const num = Number(value);
  if (Number.isNaN(num)) return "-";
  const prefix = num > 0 ? "+" : "";
  return `${prefix}${(num * 100).toFixed(2)}%`;
};

const formatNum = (value, digits = 4) => {
  if (value === null || value === undefined || value === "") return "-";
  const num = Number(value);
  if (Number.isNaN(num)) return "-";
  return num.toFixed(digits);
};

const formatDate = (value) => {
  const text = String(value || "");
  if (text.length !== 8) return text || "-";
  return `${text.slice(0, 4)}-${text.slice(4, 6)}-${text.slice(6, 8)}`;
};

const formatMoney = (value) => {
  if (value === null || value === undefined || value === "") return "-";
  const num = Number(value);
  if (Number.isNaN(num)) return "-";
  return num.toLocaleString("zh-CN", { maximumFractionDigits: 2 });
};

const renderReasonText = (reasonCodes = [], fallback = "") => {
  const codes = Array.isArray(reasonCodes) ? reasonCodes : [];
  if (!codes.length) return fallback || "-";
  return codes
    .map((code) => `${code}(${REASON_CODE_LABELS[code] || "未定义"})`)
    .join(", ");
};

const buildChartOption = (navRows = [], benchmarkRows = []) => {
  const navMap = new Map((navRows || []).map((item) => [String(item.trade_date), Number(item.nav || 0)]));
  const benchmarkCloseMap = new Map(
    (benchmarkRows || []).map((item) => [String(item.trade_date), Number(item.close || 0)])
  );
  const dates = Array.from(navMap.keys()).sort();
  const benchmarkBaseClose =
    dates.map((date) => benchmarkCloseMap.get(date) || null).find((value) => value && value > 0) || null;
  const navValues = dates.map((date) => navMap.get(date) ?? null);
  const benchmarkValues = dates.map((date) => {
    const close = benchmarkCloseMap.get(date);
    if (!benchmarkBaseClose || !close || close <= 0) return null;
    return close / benchmarkBaseClose;
  });
  return {
    backgroundColor: "transparent",
    tooltip: { trigger: "axis" },
    legend: { data: ["策略净值", `${BENCHMARK_CODE} ${BENCHMARK_NAME}`], top: 8 },
    grid: { left: 56, right: 24, top: 40, bottom: 36 },
    xAxis: {
      type: "category",
      data: dates.map((d) => formatDate(d)),
      axisLabel: { color: "#8c6f68" },
      axisLine: { lineStyle: { color: "#d9c3be" } },
    },
    yAxis: {
      type: "value",
      name: "净值",
      axisLabel: { color: "#8c6f68" },
      splitLine: { lineStyle: { color: "#f0d9d4" } },
    },
    series: [
      {
        name: "策略净值",
        type: "line",
        data: navValues,
        smooth: true,
        showSymbol: false,
        lineStyle: { color: "#2563eb", width: 2 },
        itemStyle: { color: "#2563eb" },
      },
      {
        name: `${BENCHMARK_CODE} ${BENCHMARK_NAME}`,
        type: "line",
        data: benchmarkValues,
        smooth: true,
        showSymbol: false,
        lineStyle: { color: "#e23b2e", width: 2 },
        itemStyle: { color: "#e23b2e" },
      },
    ],
  };
};

/** 仓位图：全时段仓位占比（%）+ 中证500 净值，双 Y 轴 */
const buildExposureChartOption = (navRows = [], benchmarkRows = []) => {
  const dates = (navRows || [])
    .map((item) => String(item.trade_date || ""))
    .filter(Boolean)
    .sort();
  if (!dates.length) {
    return { title: { text: "暂无数据", left: "center", top: "center" } };
  }
  const navByDate = new Map(
    (navRows || []).map((item) => [
      String(item.trade_date),
      {
        exposure: Number(item.exposure),
        cash: Number(item.cash ?? 0),
        position_value: Number(item.position_value ?? 0),
      },
    ])
  );
  const exposurePcts = dates.map((d) => {
    const row = navByDate.get(d);
    if (!row) return null;
    let pct = row.exposure;
    if (pct == null || Number.isNaN(pct)) {
      const total = row.cash + row.position_value;
      pct = total > 0 ? row.position_value / total : 0;
    }
    return Math.round(Number(pct) * 10000) / 100;
  });
  const benchmarkCloseMap = new Map(
    (benchmarkRows || []).map((item) => [String(item.trade_date), Number(item.close || 0)])
  );
  const benchmarkBaseClose =
    dates.map((d) => benchmarkCloseMap.get(d) || null).find((v) => v && v > 0) || null;
  const benchmarkValues = dates.map((d) => {
    const close = benchmarkCloseMap.get(d);
    if (!benchmarkBaseClose || !close || close <= 0) return null;
    return close / benchmarkBaseClose;
  });
  return {
    backgroundColor: "transparent",
    tooltip: { trigger: "axis" },
    legend: { data: ["仓位占比", `${BENCHMARK_CODE} ${BENCHMARK_NAME}`], top: 4 },
    grid: { left: 44, right: 44, top: 28, bottom: 28 },
    xAxis: {
      type: "category",
      data: dates.map((d) => formatDate(d)),
      axisLabel: { color: "#8c6f68", fontSize: 10 },
      axisLine: { lineStyle: { color: "#d9c3be" } },
    },
    yAxis: [
      {
        type: "value",
        name: "仓位(%)",
        min: 0,
        max: 100,
        axisLabel: { color: "#8c6f68", fontSize: 10 },
        splitLine: { lineStyle: { color: "#f0d9d4" } },
      },
      {
        type: "value",
        name: "净值",
        axisLabel: { color: "#8c6f68", fontSize: 10 },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: "仓位占比",
        type: "line",
        yAxisIndex: 0,
        data: exposurePcts,
        smooth: true,
        showSymbol: false,
        lineStyle: { color: "#2563eb", width: 2 },
        itemStyle: { color: "#2563eb" },
      },
      {
        name: `${BENCHMARK_CODE} ${BENCHMARK_NAME}`,
        type: "line",
        yAxisIndex: 1,
        data: benchmarkValues,
        smooth: true,
        showSymbol: false,
        lineStyle: { color: "#e23b2e", width: 2 },
        itemStyle: { color: "#e23b2e" },
      },
    ],
  };
};

export default function BacktestDetailPage() {
  const router = useRouter();
  const { run_id: runId } = router.query;
  const chartRef = useRef(null);
  const chartInstanceRef = useRef(null);
  const exposureChartRef = useRef(null);
  const exposureChartInstanceRef = useRef(null);
  const holdingsSummaryRef = useRef(null);
  const holdingsTooltipRef = useRef(null);
  const holdingsModalRef = useRef(null);
  const tooltipContainerRef = useRef(null);
  const tradesCacheRef = useRef(new Map());

  const [detail, setDetail] = useState(null);
  const [navItems, setNavItems] = useState([]);
  const [benchmarkItems, setBenchmarkItems] = useState([]);
  const [holdingsSummary, setHoldingsSummary] = useState([]);
  const [holdingsModalOpen, setHoldingsModalOpen] = useState(false);
  const [tradeTooltip, setTradeTooltip] = useState({
    visible: false,
    loading: false,
    title: "",
    items: [],
    x: 0,
    y: 0,
  });
  const [tradeItems, setTradeItems] = useState([]);
  const [tradeTotal, setTradeTotal] = useState(0);
  const [tradePage, setTradePage] = useState(1);
  const [tradePageSize] = useState(20);
  const [signalItems, setSignalItems] = useState([]);
  const [signalTotal, setSignalTotal] = useState(0);
  const [signalPage, setSignalPage] = useState(1);
  const [signalPageSize] = useState(20);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const summary = detail?.summary_metrics || {};
  const annualReturns = summary.annual_returns || {};
  const annualDrawdowns = summary.annual_max_drawdowns || {};
  const years = useMemo(
    () => Array.from(new Set([...Object.keys(annualReturns), ...Object.keys(annualDrawdowns)])).sort(),
    [annualReturns, annualDrawdowns]
  );
  const tradeGroups = useMemo(() => {
    const groups = [];
    let currentDate = "";
    let currentRows = [];
    tradeItems.forEach((item) => {
      const tradeDate = String(item.trade_date || "");
      if (tradeDate !== currentDate) {
        if (currentRows.length) {
          groups.push({ trade_date: currentDate, rows: currentRows });
        }
        currentDate = tradeDate;
        currentRows = [item];
      } else {
        currentRows.push(item);
      }
    });
    if (currentRows.length) {
      groups.push({ trade_date: currentDate, rows: currentRows });
    }
    return groups;
  }, [tradeItems]);

  const loadBase = useCallback(async () => {
    if (!runId) return;
    setLoading(true);
    setError("");
    try {
      const [detailRes, navRes] = await Promise.all([
        apiFetch(`/backtests/${runId}`),
        apiFetch(`/backtests/${runId}/nav`),
      ]);
      if (!detailRes.ok) throw new Error(`详情加载失败: ${detailRes.status}`);
      if (!navRes.ok) throw new Error(`净值加载失败: ${navRes.status}`);
      const detailData = await detailRes.json();
      const navData = await navRes.json();
      setDetail(detailData || null);
      setNavItems(navData.items || []);

      const benchmarkParams = new URLSearchParams();
      benchmarkParams.set("ts_code", BENCHMARK_CODE);
      benchmarkParams.set("limit", "10000");
      if (detailData?.start_date) benchmarkParams.set("start_date", String(detailData.start_date));
      if (detailData?.end_date) benchmarkParams.set("end_date", String(detailData.end_date));
      const benchmarkRes = await apiFetch(`/market-index/chart?${benchmarkParams.toString()}`);
      if (benchmarkRes.ok) {
        const benchmarkData = await benchmarkRes.json();
        setBenchmarkItems(benchmarkData.items || []);
      } else {
        setBenchmarkItems([]);
      }
    } catch (err) {
      setError(err.message || "加载失败");
    } finally {
      setLoading(false);
    }
  }, [runId]);

  const loadTrades = useCallback(async () => {
    if (!runId) return;
    try {
      const res = await apiFetch(
        `/backtests/${runId}/trades?page=${tradePage}&page_size=${tradePageSize}`
      );
      if (!res.ok) throw new Error(`交易明细加载失败: ${res.status}`);
      const data = await res.json();
      setTradeItems(data.items || []);
      setTradeTotal(data.total || 0);
    } catch (err) {
      setError(err.message || "交易明细加载失败");
    }
  }, [runId, tradePage, tradePageSize]);

  const loadHoldingsSummary = useCallback(async () => {
    if (!runId) return;
    try {
      const res = await apiFetch(`/backtests/${runId}/holdings-summary`);
      if (!res.ok) throw new Error(`持仓汇总加载失败: ${res.status}`);
      const data = await res.json();
      setHoldingsSummary(data.items || []);
    } catch {
      setHoldingsSummary([]);
    }
  }, [runId]);

  const showTradeTooltip = useCallback(
    async (event, item, containerEl) => {
      const container = containerEl || holdingsSummaryRef.current;
      if (!container) return;
      const tsCode = String(item.ts_code || "").trim();
      if (!tsCode) return;
      const cacheKey = tsCode;
      const containerRect = container.getBoundingClientRect();
      const mouseX = event.clientX - containerRect.left;
      const mouseY = event.clientY - containerRect.top;
      tooltipContainerRef.current = container;
      const x = mouseX + 12;
      const y = mouseY + 12;

      const cached = tradesCacheRef.current.get(cacheKey);
      if (cached) {
        setTradeTooltip({
          visible: true,
          loading: false,
          title: `${tsCode} 全部买卖记录`,
          items: cached,
          x,
          y,
        });
        return;
      }

      setTradeTooltip({
        visible: true,
        loading: true,
        title: `${tsCode} 全部买卖记录`,
        items: [],
        x,
        y,
      });
      try {
        const res = await apiFetch(`/backtests/${runId}/trades-by-code?ts_code=${encodeURIComponent(tsCode)}`);
        if (!res.ok) throw new Error(`交易记录加载失败: ${res.status}`);
        const data = await res.json();
        const allTrades = data.items || [];
        tradesCacheRef.current.set(cacheKey, allTrades);
        setTradeTooltip({
          visible: true,
          loading: false,
          title: `${tsCode} 全部买卖记录`,
          items: allTrades,
          x,
          y,
        });
      } catch {
        setTradeTooltip({
          visible: true,
          loading: false,
          title: `${tsCode} 全部买卖记录`,
          items: [],
          x,
          y,
        });
      }
    },
    [runId]
  );

  const hideTradeTooltip = useCallback(() => {
    setTradeTooltip((prev) => ({ ...prev, visible: false }));
  }, []);

  const moveTradeTooltip = useCallback(
    (event) => {
      const container = tooltipContainerRef.current || holdingsSummaryRef.current;
      if (!container) return;
      const containerRect = container.getBoundingClientRect();
      const mouseX = event.clientX - containerRect.left;
      const mouseY = event.clientY - containerRect.top;
      setTradeTooltip((prev) =>
        prev.visible ? { ...prev, x: mouseX + 12, y: mouseY + 12 } : prev
      );
    },
    []
  );

  useEffect(() => {
    const container = tooltipContainerRef.current || holdingsSummaryRef.current;
    if (!tradeTooltip.visible || !holdingsTooltipRef.current || !container) return;
    const containerRect = container.getBoundingClientRect();
    const tooltipRect = holdingsTooltipRef.current.getBoundingClientRect();
    let nextX = tradeTooltip.x;
    let nextY = tradeTooltip.y;
    const maxX = containerRect.width - tooltipRect.width - 8;
    const maxY = containerRect.height - tooltipRect.height - 8;
    if (nextX > maxX) nextX = Math.max(8, maxX);
    if (nextY > maxY) nextY = Math.max(8, maxY);
    if (nextX < 8) nextX = 8;
    if (nextY < 8) nextY = 8;
    if (nextX !== tradeTooltip.x || nextY !== tradeTooltip.y) {
      setTradeTooltip((prev) => ({ ...prev, x: nextX, y: nextY }));
    }
  }, [tradeTooltip.visible, tradeTooltip.x, tradeTooltip.y]);

  const loadSignals = useCallback(async () => {
    if (!runId) return;
    try {
      const res = await apiFetch(
        `/backtests/${runId}/signals?page=${signalPage}&page_size=${signalPageSize}`
      );
      if (!res.ok) throw new Error(`信号加载失败: ${res.status}`);
      const data = await res.json();
      setSignalItems(data.items || []);
      setSignalTotal(data.total || 0);
    } catch (err) {
      setError(err.message || "信号加载失败");
    }
  }, [runId, signalPage, signalPageSize]);

  useEffect(() => {
    loadBase();
  }, [loadBase]);

  useEffect(() => {
    loadTrades();
  }, [loadTrades]);

  useEffect(() => {
    loadHoldingsSummary();
  }, [loadHoldingsSummary]);

  useEffect(() => {
    loadSignals();
  }, [loadSignals]);

  useEffect(() => {
    if (!chartRef.current) return;
    if (!navItems.length) return;
    let disposed = false;
    import("echarts").then((echarts) => {
      if (disposed || !chartRef.current) return;
      if (!chartInstanceRef.current) {
        chartInstanceRef.current = echarts.init(chartRef.current);
      }
      chartInstanceRef.current.setOption(buildChartOption(navItems, benchmarkItems), true);
    });
    const handleResize = () => chartInstanceRef.current?.resize();
    window.addEventListener("resize", handleResize);
    return () => {
      disposed = true;
      window.removeEventListener("resize", handleResize);
    };
  }, [navItems, benchmarkItems]);

  useEffect(() => {
    if (!exposureChartRef.current) return;
    if (!navItems.length) return;
    let disposed = false;
    import("echarts").then((echarts) => {
      if (disposed || !exposureChartRef.current) return;
      if (!exposureChartInstanceRef.current) {
        exposureChartInstanceRef.current = echarts.init(exposureChartRef.current);
      }
      exposureChartInstanceRef.current.setOption(
        buildExposureChartOption(navItems, benchmarkItems),
        true
      );
    });
    const handleResize = () => exposureChartInstanceRef.current?.resize();
    window.addEventListener("resize", handleResize);
    return () => {
      disposed = true;
      window.removeEventListener("resize", handleResize);
    };
  }, [navItems, benchmarkItems]);

  useEffect(
    () => () => {
      chartInstanceRef.current?.dispose();
      chartInstanceRef.current = null;
      exposureChartInstanceRef.current?.dispose();
      exposureChartInstanceRef.current = null;
    },
    []
  );

  return (
    <main className="page">
      <header className="header">
        <div>
          <h1>回测: {runId || "-"}</h1>
          <p className="subtitle">
            {detail
              ? `${detail.strategy_id || "-"} / ${detail.strategy_version_id || "-"} / ${
                  detail.start_date || "-"
                } ~ ${detail.end_date || "-"}`
              : "加载中..."}
          </p>
          {runId ? (
            <p className="usage-command">
              <span className="usage-command-label">使用命令：</span>
              <code className="usage-command-code">
                python backend/scripts/backtest/run_backtest.py --run-id {runId}
              </code>
            </p>
          ) : null}
        </div>
        <div className="header-actions">
          <Link className="link-button" href="/backtests">
            返回列表
          </Link>
        </div>
      </header>

      {error ? <div className="error">{error}</div> : null}

      <div className="kpi-row">
        <div className="kpi-tile">
          <div className="kpi-tile__label">累计收益</div>
          <div className="kpi-tile__value">{formatPct(summary.total_return)}</div>
        </div>
        <div className="kpi-tile">
          <div className="kpi-tile__label">最大回撤</div>
          <div className="kpi-tile__value">{formatPct(summary.max_drawdown)}</div>
        </div>
        <div className="kpi-tile">
          <div className="kpi-tile__label">胜率</div>
          <div className="kpi-tile__value">{formatPct(summary.win_rate)}</div>
        </div>
        <div className="kpi-tile">
          <div className="kpi-tile__label">交易次数</div>
          <div className="kpi-tile__value">{summary.trade_count ?? "-"}</div>
        </div>
        <div className="kpi-tile">
          <div className="kpi-tile__label">年化收益</div>
          <div className="kpi-tile__value">{formatPct(summary.annual_return)}</div>
        </div>
        <div className="kpi-tile">
          <div className="kpi-tile__label">夏普比率</div>
          <div className="kpi-tile__value">{formatNum(summary.sharpe_ratio, 2)}</div>
        </div>
        <div className="kpi-tile">
          <div className="kpi-tile__label">状态</div>
          <div className="kpi-tile__value" style={{ fontSize: 14 }}>{detail?.status || "-"}</div>
        </div>
      </div>

      <section className="panel" style={{ marginBottom: 20 }}>
        <h3 style={{ marginTop: 0 }}>回测结果</h3>
        <div className="backtest-charts-row">
          <div
            ref={chartRef}
            className="backtest-chart-nav"
            style={{
              height: 420,
              border: "1px solid var(--border-light)",
              borderRadius: 12,
            }}
          />
          <div className="backtest-chart-right">
            <div
              ref={exposureChartRef}
              className="backtest-chart-exposure"
              style={{
                border: "1px solid var(--border-light)",
                borderRadius: 12,
              }}
            />
            <div className="backtest-chart-placeholder">
              <div
                className="holdings-summary"
                ref={holdingsSummaryRef}
                onMouseLeave={hideTradeTooltip}
                onMouseMove={moveTradeTooltip}
              >
                <div className="holdings-summary-title">
                  <button
                    type="button"
                    className="link-button holdings-summary-title-btn"
                    onClick={() => setHoldingsModalOpen(true)}
                  >
                    持有过的股票（最终收益）
                  </button>
                </div>
                {holdingsSummary.length === 0 ? (
                  <div className="holdings-summary-empty">暂无数据</div>
                ) : (
                  <div className="holdings-summary-list">
                    {holdingsSummary.map((item) => (
                      <div
                        key={item.ts_code}
                        className="holdings-summary-row"
                        onMouseEnter={(event) => showTradeTooltip(event, item, holdingsSummaryRef.current)}
                      >
                        <span className="holdings-summary-code">{item.ts_code}</span>
                        <span className="holdings-summary-name">{item.stock_name || "-"}</span>
                        <span className="holdings-summary-date">{formatDate(item.trade_date)}</span>
                        <span className="holdings-summary-return">{formatPct(item.return_pct)}</span>
                      </div>
                    ))}
                  </div>
                )}
                {tradeTooltip.visible && tooltipContainerRef.current === holdingsSummaryRef.current ? (
                  <div
                    className="holdings-tooltip"
                    style={{ left: tradeTooltip.x, top: tradeTooltip.y }}
                    ref={holdingsTooltipRef}
                  >
                    <div className="holdings-tooltip-title">{tradeTooltip.title}</div>
                    {tradeTooltip.loading ? (
                      <div className="holdings-tooltip-loading">加载中...</div>
                    ) : tradeTooltip.items.length === 0 ? (
                      <div className="holdings-tooltip-empty">当年无交易记录</div>
                    ) : (
                      <div className="holdings-tooltip-list">
                        {tradeTooltip.items.map((row, idx) => (
                          <div key={`${row.trade_date}-${row.side}-${idx}`} className="holdings-tooltip-row">
                            <span>{formatDate(row.trade_date)}</span>
                            <span className={row.side === "BUY" ? "trade-buy" : "trade-sell"}>
                              {row.side || "-"}
                            </span>
                            <span>{formatNum(row.price, 3)}</span>
                            <span>{row.qty}</span>
                            <span>{formatNum(row.amount, 2)}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ) : null}
              </div>
            </div>
          </div>
        </div>
        <p className="subtitle" style={{ marginTop: 6, marginBottom: 0 }}>
          左图：策略净值 vs 000905.SH 中证500；右上：全时段仓位占比 + 中证500；右下：持有过的股票与最终收益
        </p>
      </section>

      <section className="panel compact-panel" style={{ marginBottom: 14 }}>
        <h3 style={{ marginTop: 0, marginBottom: 8 }}>年度表现</h3>
        <div className="table-wrap compact-table">
          <table>
            <thead>
              <tr>
                <th>年份</th>
                <th>年化收益</th>
                <th>最大回撤</th>
              </tr>
            </thead>
            <tbody>
              {years.length === 0 ? (
                <tr>
                  <td colSpan={3} className="empty">
                    暂无年度数据
                  </td>
                </tr>
              ) : (
                years.map((year) => (
                  <tr key={year}>
                    <td>{year}</td>
                    <td>{formatPct(annualReturns[year])}</td>
                    <td>{formatPct(annualDrawdowns[year])}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      {holdingsModalOpen ? (
        <div
          className="modal-backdrop"
          onClick={(event) => {
            if (event.target === event.currentTarget) setHoldingsModalOpen(false);
          }}
        >
          <div className="modal-card holdings-modal" ref={holdingsModalRef} onMouseMove={moveTradeTooltip}>
            <div className="modal-header">
              <h3 style={{ margin: 0 }}>持有过的股票（最终收益）</h3>
              <button type="button" className="link-button" onClick={() => setHoldingsModalOpen(false)}>
                关闭
              </button>
            </div>
            <div className="table-wrap compact-table">
              <table>
                <thead>
                  <tr>
                    <th>代码</th>
                    <th>名称</th>
                    <th>最后持有日</th>
                    <th>最终收益</th>
                  </tr>
                </thead>
                <tbody>
                  {holdingsSummary.length === 0 ? (
                    <tr>
                      <td colSpan={4} className="empty">
                        暂无数据
                      </td>
                    </tr>
                  ) : (
                    holdingsSummary.map((item) => (
                      <tr
                        key={`modal-${item.ts_code}`}
                        onMouseEnter={(event) => showTradeTooltip(event, item, holdingsModalRef.current)}
                        onMouseLeave={hideTradeTooltip}
                      >
                        <td>{item.ts_code}</td>
                        <td>{item.stock_name || "-"}</td>
                        <td>{formatDate(item.trade_date)}</td>
                        <td>{formatPct(item.return_pct)}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
            {tradeTooltip.visible && tooltipContainerRef.current === holdingsModalRef.current ? (
              <div
                className="holdings-tooltip"
                style={{ left: tradeTooltip.x, top: tradeTooltip.y }}
                ref={holdingsTooltipRef}
              >
                <div className="holdings-tooltip-title">{tradeTooltip.title}</div>
                {tradeTooltip.loading ? (
                  <div className="holdings-tooltip-loading">加载中...</div>
                ) : tradeTooltip.items.length === 0 ? (
                  <div className="holdings-tooltip-empty">暂无交易记录</div>
                ) : (
                  <div className="holdings-tooltip-list">
                    {tradeTooltip.items.map((row, idx) => (
                      <div key={`${row.trade_date}-${row.side}-${idx}`} className="holdings-tooltip-row">
                        <span>{formatDate(row.trade_date)}</span>
                        <span className={row.side === "BUY" ? "trade-buy" : "trade-sell"}>{row.side || "-"}</span>
                        <span>{formatNum(row.price, 3)}</span>
                        <span>{row.qty}</span>
                        <span>{formatNum(row.amount, 2)}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ) : null}
          </div>
        </div>
      ) : null}

      <section className="panel compact-panel" style={{ marginBottom: 8 }}>
        <h3 style={{ marginTop: 0, marginBottom: 8 }}>交易明细</h3>
        <p className="subtitle" style={{ marginTop: 0, marginBottom: 8 }}>
          说明: `方向` 是实际成交方向（BUY/SELL）；`信号` 是策略触发类型（如 BUY_ROTATE、SELL_ROTATE）。
        </p>
        <div className="table-wrap compact-table trade-details-table">
          <table>
            <thead>
              <tr>
                <th>交易日</th>
                <th>代码</th>
                <th>名称</th>
                <th>方向</th>
                <th>信号</th>
                <th>价格</th>
                <th>数量</th>
                <th>金额</th>
                <th>原因</th>
                <th>持仓情况</th>
              </tr>
            </thead>
            <tbody>
              {tradeGroups.length === 0 ? (
                <tr>
                  <td colSpan={10} className="empty">
                    暂无交易
                  </td>
                </tr>
              ) : (
                tradeGroups.map((group) =>
                  group.rows.map((item, index) => {
                    const rowKey = item.trade_uid || `${item.trade_date}-${item.ts_code}-${item.side}-${index}`;
                    const rowSpan = group.rows.length;
                    return (
                      <tr key={rowKey}>
                        {index === 0 ? (
                          <td rowSpan={rowSpan} className="trade-date-cell">
                            {group.trade_date}
                          </td>
                        ) : null}
                        <td className="trade-code-cell">{item.ts_code}</td>
                        <td>{item.stock_name || "-"}</td>
                        <td>{item.side}</td>
                        <td>{item.signal_type || "-"}</td>
                        <td>{formatNum(item.price, 3)}</td>
                        <td>{item.qty}</td>
                        <td>{formatNum(item.amount, 2)}</td>
                        <td>{renderReasonText(item.reason_codes, item.can_trade_reason || "-")}</td>
                        {index === 0 ? (
                          <td rowSpan={rowSpan} className="holdings-cell">
                            {Array.isArray(item.wallet_holdings) && item.wallet_holdings.length > 0 ? (
                              <div className="holdings-list">
                                <div className="holdings-row holdings-header">
                                  <span>代码</span>
                                  <span>名称</span>
                                  <span className="holdings-return">收益率</span>
                                  <span className="holdings-value">市值</span>
                                </div>
                                {item.wallet_holdings.map((h) => (
                                  <div key={h.ts_code} className="holdings-row">
                                    <span className="holdings-code">{h.ts_code}</span>
                                    <span className="holdings-name">{h.name || "-"}</span>
                                    <span className="holdings-return">{formatPct(h.return_pct)}</span>
                                    <span className="holdings-value">{formatMoney(h.market_value)}</span>
                                  </div>
                                ))}
                                <div className="trade-holdings-summary">
                                  <span>持仓: {item.wallet_holding_count ?? 0}</span>
                                  <span>持仓市值: {formatMoney(item.wallet_position_value)}</span>
                                  <span>现金: {formatMoney(item.wallet_cash)}</span>
                                  <span>总资产: {formatMoney(item.wallet_total_asset)}</span>
                                </div>
                              </div>
                            ) : item.wallet_holdings_text ? (
                              <div className="trade-holdings-summary">
                                <span>{`${item.wallet_holdings_text} (共${item.wallet_holding_count || 0}只)`}</span>
                                <span>持仓市值: {formatMoney(item.wallet_position_value)}</span>
                                <span>现金: {formatMoney(item.wallet_cash)}</span>
                                <span>总资产: {formatMoney(item.wallet_total_asset)}</span>
                              </div>
                            ) : (
                              "-"
                            )}
                          </td>
                        ) : null}
                      </tr>
                    );
                  })
                )
              )}
            </tbody>
          </table>
        </div>
      </section>
      <div className="pagination compact-pagination" style={{ marginBottom: 14 }}>
        <span>
          交易记录: 共 {tradeTotal} 条，第 {tradePage} / {Math.max(Math.ceil(tradeTotal / tradePageSize), 1)} 页
        </span>
        <div className="pager-actions">
          <button type="button" disabled={tradePage <= 1} onClick={() => setTradePage((v) => Math.max(v - 1, 1))}>
            上一页
          </button>
          <button
            type="button"
            disabled={tradePage >= Math.max(Math.ceil(tradeTotal / tradePageSize), 1)}
            onClick={() =>
              setTradePage((v) => Math.min(v + 1, Math.max(Math.ceil(tradeTotal / tradePageSize), 1)))
            }
          >
            下一页
          </button>
        </div>
      </div>

      <section className="panel compact-panel" style={{ marginBottom: 8 }}>
        <h3 style={{ marginTop: 0, marginBottom: 8 }}>信号明细</h3>
        <div className="table-wrap compact-table">
          <table>
            <thead>
              <tr>
                <th>信号日</th>
                <th>代码</th>
                <th>名称</th>
                <th>信号</th>
                <th>分数</th>
                <th>目标权重</th>
                <th>目标金额</th>
                <th>原因</th>
              </tr>
            </thead>
            <tbody>
              {signalItems.length === 0 ? (
                <tr>
                  <td colSpan={8} className="empty">
                    暂无信号
                  </td>
                </tr>
              ) : (
                signalItems.map((item) => (
                  <tr key={`${item.trade_date}-${item.ts_code}`}>
                    <td>{item.trade_date}</td>
                    <td>{item.ts_code}</td>
                    <td>{item.stock_name || "-"}</td>
                    <td>{item.signal}</td>
                    <td>{formatNum(item.score, 2)}</td>
                    <td>{formatPct(item.target_weight)}</td>
                    <td>{formatNum(item.target_amount, 2)}</td>
                    <td>{renderReasonText(item.reason_codes, "-")}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>
      <div className="pagination compact-pagination">
        <span>
          信号记录: 共 {signalTotal} 条，第 {signalPage} / {Math.max(Math.ceil(signalTotal / signalPageSize), 1)} 页
        </span>
        <div className="pager-actions">
          <button type="button" disabled={signalPage <= 1} onClick={() => setSignalPage((v) => Math.max(v - 1, 1))}>
            上一页
          </button>
          <button
            type="button"
            disabled={signalPage >= Math.max(Math.ceil(signalTotal / signalPageSize), 1)}
            onClick={() =>
              setSignalPage((v) => Math.min(v + 1, Math.max(Math.ceil(signalTotal / signalPageSize), 1)))
            }
          >
            下一页
          </button>
        </div>
      </div>

      {loading ? <div className="subtitle" style={{ marginTop: 20 }}>加载中...</div> : null}
    </main>
  );
}
