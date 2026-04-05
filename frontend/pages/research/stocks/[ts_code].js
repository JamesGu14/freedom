import Link from "next/link";
import { useRouter } from "next/router";
import { useEffect, useMemo, useRef, useState } from "react";
import { apiFetch } from "../../../lib/api";
import {
  buildChipChartRows,
  buildChipDistributionOption,
  buildChipPerfChartOption,
  buildCrossBorderHoldOption,
  buildCrossBorderHoldRows,
  buildDividendChartOption,
  buildDividendChartRows,
  buildEventTimelineRows,
  buildFinancialChartOption,
  buildFinancialChartRows,
  buildFinancialSummaryStats,
  buildFlowChartRows,
  buildHolderChartRows,
  buildHolderTrendOption,
  buildMarginChartOption,
  buildMoneyflowBreakdownOption,
  buildMoneyflowChartOption,
  formatAxisUnit,
} from "../../../lib/research-charts.mjs";

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

const toLabel = (key) =>
  String(key || "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());

const renderKeyValue = (items) => (
  <div className="research-key-value-grid">
    {items.map((item) => (
      <div key={item.label} className="research-key-value-item">
        <span>{item.label}</span>
        <strong>{item.value ?? "-"}</strong>
      </div>
    ))}
  </div>
);

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

export default function StockResearchPage() {
  const router = useRouter();
  const tsCode = useMemo(() => String(router.query.ts_code || "").toUpperCase(), [router.query.ts_code]);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [overview, setOverview] = useState(null);
  const [financials, setFinancials] = useState(null);
  const [dividends, setDividends] = useState(null);
  const [holders, setHolders] = useState(null);
  const [chips, setChips] = useState(null);
  const [flows, setFlows] = useState(null);
  const [events, setEvents] = useState(null);
  const [financialView, setFinancialView] = useState("quarterly");
  const [financialMetricMode, setFinancialMetricMode] = useState("raw");
  const [flowWindow, setFlowWindow] = useState(60);

  const financialChartRef = useRef(null);
  const financialChartInstanceRef = useRef(null);
  const moneyflowChartRef = useRef(null);
  const moneyflowChartInstanceRef = useRef(null);
  const marginChartRef = useRef(null);
  const marginChartInstanceRef = useRef(null);
  const holderTrendChartRef = useRef(null);
  const holderTrendChartInstanceRef = useRef(null);
  const chipPerfChartRef = useRef(null);
  const chipPerfChartInstanceRef = useRef(null);
  const chipDistributionChartRef = useRef(null);
  const chipDistributionChartInstanceRef = useRef(null);
  const crossBorderChartRef = useRef(null);
  const crossBorderChartInstanceRef = useRef(null);
  const dividendChartRef = useRef(null);
  const dividendChartInstanceRef = useRef(null);
  const moneyflowBreakdownChartRef = useRef(null);
  const moneyflowBreakdownChartInstanceRef = useRef(null);

  useEffect(() => {
    if (!tsCode) return;
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      setError("");
      try {
        const paths = [
          `/research/stocks/${encodeURIComponent(tsCode)}/overview`,
          `/research/stocks/${encodeURIComponent(tsCode)}/financials?limit=24`,
          `/research/stocks/${encodeURIComponent(tsCode)}/dividends`,
          `/research/stocks/${encodeURIComponent(tsCode)}/holders`,
          `/research/stocks/${encodeURIComponent(tsCode)}/chips`,
          `/research/stocks/${encodeURIComponent(tsCode)}/flows`,
          `/research/stocks/${encodeURIComponent(tsCode)}/events`,
        ];
        const responses = await Promise.all(paths.map((path) => apiFetch(path)));
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
        setOverview(payloads[0]);
        setFinancials(payloads[1]);
        setDividends(payloads[2]);
        setHolders(payloads[3]);
        setChips(payloads[4]);
        setFlows(payloads[5]);
        setEvents(payloads[6]);
      } catch (err) {
        if (cancelled) return;
        setError(err.message || "加载失败");
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => {
      cancelled = true;
    };
  }, [tsCode]);

  const headerTitle = [
    tsCode,
    overview?.basic?.name,
    overview?.basic?.industry,
    "研究数据中心",
  ]
    .filter(Boolean)
    .join(" · ");

  const quarterlyFinancialRows = useMemo(() => buildFinancialChartRows(financials, "quarterly"), [financials]);
  const annualFinancialRows = useMemo(() => buildFinancialChartRows(financials, "annual"), [financials]);
  const financialChartRows = financialView === "annual" ? annualFinancialRows : quarterlyFinancialRows;
  const financialSummaryStats = useMemo(() => buildFinancialSummaryStats(quarterlyFinancialRows), [quarterlyFinancialRows]);
  const flowChartRows = useMemo(() => buildFlowChartRows(flows, flowWindow), [flowWindow, flows]);
  const holderChartRows = useMemo(() => buildHolderChartRows(holders), [holders]);
  const chipChartRows = useMemo(() => buildChipChartRows(chips), [chips]);
  const crossBorderRows = useMemo(() => buildCrossBorderHoldRows(flows), [flows]);
  const eventTimelineRows = useMemo(() => buildEventTimelineRows(events), [events]);
  const dividendChartRows = useMemo(() => buildDividendChartRows(dividends), [dividends]);

  useEffect(() => {
    let mounted = true;
    const renderChart = async () => {
      if (!financialChartRef.current || financialChartRows.length === 0) return;
      const echartsModule = await import("echarts");
      const echarts = echartsModule?.default ?? echartsModule;
      if (!mounted || !echarts?.init || !financialChartRef.current) return;
      if (!financialChartInstanceRef.current) {
        financialChartInstanceRef.current = echarts.init(financialChartRef.current, null, { renderer: "canvas" });
      }
      financialChartInstanceRef.current.setOption(buildFinancialChartOption(financialChartRows, financialView, financialMetricMode), { notMerge: true });
      financialChartInstanceRef.current.resize();
    };
    renderChart();
    const onResize = () => financialChartInstanceRef.current?.resize();
    window.addEventListener("resize", onResize);
    return () => {
      mounted = false;
      window.removeEventListener("resize", onResize);
    };
  }, [financialChartRows, financialMetricMode, financialView]);

  useEffect(() => {
    let mounted = true;
    const renderChart = async () => {
      if (!moneyflowChartRef.current || flowChartRows.moneyflow.length === 0) return;
      const echartsModule = await import("echarts");
      const echarts = echartsModule?.default ?? echartsModule;
      if (!mounted || !echarts?.init || !moneyflowChartRef.current) return;
      if (!moneyflowChartInstanceRef.current) {
        moneyflowChartInstanceRef.current = echarts.init(moneyflowChartRef.current, null, { renderer: "canvas" });
      }
      moneyflowChartInstanceRef.current.setOption(buildMoneyflowChartOption(flowChartRows.moneyflow), { notMerge: true });
      moneyflowChartInstanceRef.current.resize();
    };
    renderChart();
    const onResize = () => moneyflowChartInstanceRef.current?.resize();
    window.addEventListener("resize", onResize);
    return () => {
      mounted = false;
      window.removeEventListener("resize", onResize);
    };
  }, [flowChartRows]);

  useEffect(() => {
    let mounted = true;
    const renderChart = async () => {
      if (!holderTrendChartRef.current || holderChartRows.length === 0) return;
      const echartsModule = await import("echarts");
      const echarts = echartsModule?.default ?? echartsModule;
      if (!mounted || !echarts?.init || !holderTrendChartRef.current) return;
      if (!holderTrendChartInstanceRef.current) {
        holderTrendChartInstanceRef.current = echarts.init(holderTrendChartRef.current, null, { renderer: "canvas" });
      }
      holderTrendChartInstanceRef.current.setOption(buildHolderTrendOption(holderChartRows), { notMerge: true });
      holderTrendChartInstanceRef.current.resize();
    };
    renderChart();
    const onResize = () => holderTrendChartInstanceRef.current?.resize();
    window.addEventListener("resize", onResize);
    return () => {
      mounted = false;
      window.removeEventListener("resize", onResize);
    };
  }, [holderChartRows]);

  useEffect(() => {
    let mounted = true;
    const renderChart = async () => {
      if (!chipPerfChartRef.current || chipChartRows.perf.length === 0) return;
      const echartsModule = await import("echarts");
      const echarts = echartsModule?.default ?? echartsModule;
      if (!mounted || !echarts?.init || !chipPerfChartRef.current) return;
      if (!chipPerfChartInstanceRef.current) {
        chipPerfChartInstanceRef.current = echarts.init(chipPerfChartRef.current, null, { renderer: "canvas" });
      }
      chipPerfChartInstanceRef.current.setOption(buildChipPerfChartOption(chipChartRows.perf), { notMerge: true });
      chipPerfChartInstanceRef.current.resize();
    };
    renderChart();
    const onResize = () => chipPerfChartInstanceRef.current?.resize();
    window.addEventListener("resize", onResize);
    return () => {
      mounted = false;
      window.removeEventListener("resize", onResize);
    };
  }, [chipChartRows]);

  useEffect(() => {
    let mounted = true;
    const renderChart = async () => {
      if (!crossBorderChartRef.current || crossBorderRows.length === 0) return;
      const echartsModule = await import("echarts");
      const echarts = echartsModule?.default ?? echartsModule;
      if (!mounted || !echarts?.init || !crossBorderChartRef.current) return;
      if (!crossBorderChartInstanceRef.current) {
        crossBorderChartInstanceRef.current = echarts.init(crossBorderChartRef.current, null, { renderer: "canvas" });
      }
      crossBorderChartInstanceRef.current.setOption(buildCrossBorderHoldOption(crossBorderRows), { notMerge: true });
      crossBorderChartInstanceRef.current.resize();
    };
    renderChart();
    const onResize = () => crossBorderChartInstanceRef.current?.resize();
    window.addEventListener("resize", onResize);
    return () => {
      mounted = false;
      window.removeEventListener("resize", onResize);
    };
  }, [crossBorderRows]);

  useEffect(() => {
    let mounted = true;
    const renderChart = async () => {
      if (!dividendChartRef.current || dividendChartRows.length === 0) return;
      const echartsModule = await import("echarts");
      const echarts = echartsModule?.default ?? echartsModule;
      if (!mounted || !echarts?.init || !dividendChartRef.current) return;
      if (!dividendChartInstanceRef.current) {
        dividendChartInstanceRef.current = echarts.init(dividendChartRef.current, null, { renderer: "canvas" });
      }
      dividendChartInstanceRef.current.setOption(buildDividendChartOption(dividendChartRows), { notMerge: true });
      dividendChartInstanceRef.current.resize();
    };
    renderChart();
    const onResize = () => dividendChartInstanceRef.current?.resize();
    window.addEventListener("resize", onResize);
    return () => {
      mounted = false;
      window.removeEventListener("resize", onResize);
    };
  }, [dividendChartRows]);

  useEffect(() => {
    let mounted = true;
    const renderChart = async () => {
      if (!moneyflowBreakdownChartRef.current || flowChartRows.moneyflow.length === 0) return;
      const echartsModule = await import("echarts");
      const echarts = echartsModule?.default ?? echartsModule;
      if (!mounted || !echarts?.init || !moneyflowBreakdownChartRef.current) return;
      if (!moneyflowBreakdownChartInstanceRef.current) {
        moneyflowBreakdownChartInstanceRef.current = echarts.init(moneyflowBreakdownChartRef.current, null, { renderer: "canvas" });
      }
      moneyflowBreakdownChartInstanceRef.current.setOption(buildMoneyflowBreakdownOption(flowChartRows.moneyflow), { notMerge: true });
      moneyflowBreakdownChartInstanceRef.current.resize();
    };
    renderChart();
    const onResize = () => moneyflowBreakdownChartInstanceRef.current?.resize();
    window.addEventListener("resize", onResize);
    return () => {
      mounted = false;
      window.removeEventListener("resize", onResize);
    };
  }, [flowChartRows]);

  useEffect(() => {
    let mounted = true;
    const renderChart = async () => {
      if (!chipDistributionChartRef.current || chipChartRows.distribution.length === 0) return;
      const echartsModule = await import("echarts");
      const echarts = echartsModule?.default ?? echartsModule;
      if (!mounted || !echarts?.init || !chipDistributionChartRef.current) return;
      if (!chipDistributionChartInstanceRef.current) {
        chipDistributionChartInstanceRef.current = echarts.init(chipDistributionChartRef.current, null, { renderer: "canvas" });
      }
      chipDistributionChartInstanceRef.current.setOption(buildChipDistributionOption(chipChartRows.distribution, chipChartRows.latestTradeDate), { notMerge: true });
      chipDistributionChartInstanceRef.current.resize();
    };
    renderChart();
    const onResize = () => chipDistributionChartInstanceRef.current?.resize();
    window.addEventListener("resize", onResize);
    return () => {
      mounted = false;
      window.removeEventListener("resize", onResize);
    };
  }, [chipChartRows]);

  useEffect(() => {
    let mounted = true;
    const renderChart = async () => {
      if (!marginChartRef.current || flowChartRows.margin.length === 0) return;
      const echartsModule = await import("echarts");
      const echarts = echartsModule?.default ?? echartsModule;
      if (!mounted || !echarts?.init || !marginChartRef.current) return;
      if (!marginChartInstanceRef.current) {
        marginChartInstanceRef.current = echarts.init(marginChartRef.current, null, { renderer: "canvas" });
      }
      marginChartInstanceRef.current.setOption(buildMarginChartOption(flowChartRows.margin), { notMerge: true });
      marginChartInstanceRef.current.resize();
    };
    renderChart();
    const onResize = () => marginChartInstanceRef.current?.resize();
    window.addEventListener("resize", onResize);
    return () => {
      mounted = false;
      window.removeEventListener("resize", onResize);
    };
  }, [flowChartRows]);

  useEffect(() => () => {
    financialChartInstanceRef.current?.dispose();
    financialChartInstanceRef.current = null;
    moneyflowChartInstanceRef.current?.dispose();
    moneyflowChartInstanceRef.current = null;
    marginChartInstanceRef.current?.dispose();
    marginChartInstanceRef.current = null;
    holderTrendChartInstanceRef.current?.dispose();
    holderTrendChartInstanceRef.current = null;
    chipPerfChartInstanceRef.current?.dispose();
    chipPerfChartInstanceRef.current = null;
    chipDistributionChartInstanceRef.current?.dispose();
    chipDistributionChartInstanceRef.current = null;
    crossBorderChartInstanceRef.current?.dispose();
    crossBorderChartInstanceRef.current = null;
    dividendChartInstanceRef.current?.dispose();
    dividendChartInstanceRef.current = null;
    moneyflowBreakdownChartInstanceRef.current?.dispose();
    moneyflowBreakdownChartInstanceRef.current = null;
  }, []);

  return (
    <main className="page">
      <header className="header">
        <div>
          <p className="eyebrow">Research</p>
          <h1>{headerTitle || "个股研究"}</h1>
          <p className="subtitle">把财务、分红、股东、筹码、资金流和事件数据集中展示。</p>
        </div>
        <div className="research-header-actions">
          <Link className="link-button" href={`/stocks/${encodeURIComponent(tsCode || "000001.SZ")}`}>
            返回个股页
          </Link>
          <Link className="primary" href="/research">
            研究中心
          </Link>
        </div>
      </header>

      {error ? <div className="error">{error}</div> : null}
      {loading ? <div className="panel"><p className="subtitle">加载中...</p></div> : null}

      {overview ? (
        <section className="panel">
          <div className="panel-title-row">
            <h2>摘要</h2>
            <span className="badge">{overview?.latest_daily?.trade_date ? formatDate(overview.latest_daily.trade_date) : "无最新交易日"}</span>
          </div>
          {renderKeyValue([
            { label: "最新收盘", value: formatNum(overview?.latest_daily?.close) },
            { label: "最新PE", value: formatNum(overview?.latest_daily_basic?.pe) },
            { label: "最新PB", value: formatNum(overview?.latest_daily_basic?.pb) },
            { label: "最新ROE", value: formatNum(overview?.latest_financial_indicator?.roe) },
            { label: "最近分红公告", value: formatDate(overview?.latest_dividend_summary?.latest_ann_date) },
            { label: "最近股东人数", value: overview?.latest_holder_summary?.latest_holder_num ?? "-" },
            { label: "最近主力净流入", value: formatNum(overview?.latest_flow_summary?.moneyflow_dc) },
            { label: "最近停复牌", value: formatDate(overview?.latest_event_summary?.latest_suspend_date) },
          ])}
        </section>
      ) : null}

      {financials ? (
        <section className="research-section-grid">
          <section className="panel">
            <div className="panel-title-row">
              <h2>财务与分红</h2>
              <div className="research-toolbar-stack">
                <div className="indicator-switcher">
                  <span className="indicator-switcher-label">报告期</span>
                  <button type="button" className={`indicator-switcher-btn ${financialView === "quarterly" ? "active" : ""}`} onClick={() => setFinancialView("quarterly")}>
                    季度
                  </button>
                  <button type="button" className={`indicator-switcher-btn ${financialView === "annual" ? "active" : ""}`} onClick={() => setFinancialView("annual")}>
                    年度
                  </button>
                </div>
                <div className="indicator-switcher">
                  <span className="indicator-switcher-label">指标</span>
                  <button type="button" className={`indicator-switcher-btn ${financialMetricMode === "raw" ? "active" : ""}`} onClick={() => setFinancialMetricMode("raw")}>
                    原始值
                  </button>
                  <button type="button" className={`indicator-switcher-btn ${financialMetricMode === "yoy" ? "active" : ""}`} onClick={() => setFinancialMetricMode("yoy")}>
                    同比
                  </button>
                  <button type="button" className={`indicator-switcher-btn ${financialMetricMode === "ttm" ? "active" : ""}`} onClick={() => setFinancialMetricMode("ttm")}>
                    TTM
                  </button>
                </div>
              </div>
            </div>
            {renderKeyValue([
              { label: "最近报告期", value: formatDate(financials.latest_period) },
              { label: "EPS", value: formatNum(financials?.indicators?.[0]?.eps) },
              { label: "ROE", value: formatNum(financials?.indicators?.[0]?.roe) },
              { label: "ROA", value: formatNum(financials?.indicators?.[0]?.roa) },
              { label: "毛利率", value: formatNum(financials?.indicators?.[0]?.grossprofit_margin) },
              { label: "资产负债率", value: formatNum(financials?.indicators?.[0]?.debt_to_assets) },
              { label: "营收同比", value: financialSummaryStats?.revenue_yoy == null ? "-" : `${formatNum(financialSummaryStats.revenue_yoy)}%` },
              { label: "净利润同比", value: financialSummaryStats?.n_income_yoy == null ? "-" : `${formatNum(financialSummaryStats.n_income_yoy)}%` },
              { label: "营收TTM", value: formatAxisUnit(financialSummaryStats?.revenue_ttm) },
              { label: "净利润TTM", value: formatAxisUnit(financialSummaryStats?.n_income_ttm) },
              { label: "最近现金分红", value: formatNum(dividends?.summary?.latest_cash_div) },
              { label: "连续分红年数", value: dividends?.summary?.consecutive_years ?? "-" },
            ])}
            <p className="subtitle research-chart-note">
              {financialMetricMode === "raw"
                ? "金额按原始报告值展示，比率沿用最新财务指标。"
                : financialMetricMode === "yoy"
                  ? "同比模式对营收、净利润和经营现金流计算同口径增速，比率曲线保持原值。"
                  : "TTM 模式使用滚动四季口径，更适合看盈利和现金流趋势。"}
            </p>
            <div className="research-chart-canvas" ref={financialChartRef} />
            <div className="research-chart-grid">
              <div>
                <h3>分红送股趋势</h3>
                <div className="research-chart-canvas research-chart-canvas--compact" ref={dividendChartRef} />
              </div>
            </div>
          </section>
        </section>
      ) : null}

      <section className="research-section-grid">
        <section className="panel">
          <h2>股东结构</h2>
          {renderKeyValue([
            { label: "最新股东人数", value: holders?.summary?.latest_holder_num ?? "-" },
            { label: "股东人数变化", value: holders?.summary?.holder_num_change ?? "-" },
            { label: "前十大集中度", value: holders?.summary?.top10_holder_ratio ?? "-" },
            { label: "前十大流通集中度", value: holders?.summary?.top10_float_holder_ratio ?? "-" },
          ])}
          <p className="subtitle research-chart-note">用一张趋势图同时看股东人数变化和前十大集中度，比单看表格更容易发现筹码收敛或扩散。</p>
          <div className="research-chart-canvas research-chart-canvas--compact" ref={holderTrendChartRef} />
        </section>
        <section className="panel">
          <h2>筹码结构</h2>
          {renderKeyValue([
            { label: "最新筹码日期", value: formatDate(chips?.summary?.latest_trade_date) },
            { label: "筹码集中指标", value: formatNum(chips?.summary?.latest_cost_focus) },
            { label: "获利比例", value: formatNum(chips?.summary?.latest_profit_ratio) },
            { label: "加权成本", value: formatNum(chips?.summary?.latest_weight_avg) },
          ])}
          <div className="research-chart-grid">
            <div>
              <h3>筹码绩效趋势</h3>
              <div className="research-chart-canvas research-chart-canvas--compact" ref={chipPerfChartRef} />
            </div>
            <div>
              <h3>最新筹码分布</h3>
              <div className="research-chart-canvas research-chart-canvas--compact" ref={chipDistributionChartRef} />
            </div>
          </div>
        </section>
      </section>

      <section className="research-section-grid">
        <section className="panel">
          <div className="panel-title-row">
            <h2>两融与资金流摘要</h2>
            <div className="indicator-switcher">
              <span className="indicator-switcher-label">窗口</span>
              {[30, 60, 120].map((days) => (
                <button
                  key={days}
                  type="button"
                  className={`indicator-switcher-btn ${flowWindow === days ? "active" : ""}`}
                  onClick={() => setFlowWindow(days)}
                >
                  {days}天
                </button>
              ))}
            </div>
          </div>
          {renderKeyValue([
            { label: "主力净流入", value: formatNum(flows?.summary?.moneyflow_dc) },
            { label: "融资余额", value: formatNum(flows?.summary?.margin_rzye) },
            { label: "融资余额变化", value: formatNum(flows?.summary?.margin_rzye_change) },
            { label: "港股通持股", value: formatNum(flows?.summary?.hk_hold_vol) },
            { label: "CCASS 持股比例", value: formatNum(flows?.summary?.ccass_hold_ratio) },
          ])}
          <div className="research-chart-grid">
            <div>
              <h3>主力净流入趋势</h3>
              <div className="research-chart-canvas research-chart-canvas--compact" ref={moneyflowChartRef} />
            </div>
            <div>
              <h3>两融余额趋势</h3>
              <div className="research-chart-canvas research-chart-canvas--compact" ref={marginChartRef} />
            </div>
          </div>
          <div className="research-chart-grid">
            <div>
              <h3>资金流买入构成</h3>
              <div className="research-chart-canvas research-chart-canvas--compact" ref={moneyflowBreakdownChartRef} />
            </div>
            <div>
              <h3>港股通与 CCASS 持股趋势</h3>
              <div className="research-chart-canvas research-chart-canvas--compact" ref={crossBorderChartRef} />
            </div>
          </div>
        </section>
      </section>

      <section className="research-section-grid">
        <section className="panel">
          <h2>停复牌与事件摘要</h2>
          {renderKeyValue([
            { label: "最近停牌日", value: formatDate(events?.summary?.latest_suspend_date) },
            { label: "停牌类型", value: events?.summary?.latest_suspend_type ?? "-" },
            { label: "最近调研日", value: formatDate(events?.summary?.latest_survey_date) },
            { label: "最近调研机构", value: events?.summary?.latest_survey_org ?? "-" },
          ])}
          <div className="research-timeline">
            {eventTimelineRows.length > 0 ? eventTimelineRows.map((item, index) => (
              <article key={`${item.kind}-${item.date}-${index}`} className="research-timeline-item">
                <div className={`research-timeline-dot research-timeline-dot--${item.kind}`} />
                <div className="research-timeline-content">
                  <div className="research-timeline-meta">
                    <span className="badge">{formatDate(item.date)}</span>
                    <strong>{item.subtitle}</strong>
                  </div>
                  <h3>{item.title}</h3>
                  <p>{item.detail}</p>
                </div>
              </article>
            )) : <div className="empty">暂无事件时间线</div>}
          </div>
        </section>
      </section>

      <section className="panel">
        <h2>研究明细表</h2>
        <p className="subtitle">趋势和结构优先看图表，逐行核对时再展开原始明细。</p>
        <div className="research-detail-stack">
          <details className="research-detail-card">
            <summary>财务与分红明细</summary>
            <div className="research-detail-body">
              <TableSection
                title="财务指标"
                rows={financials?.indicators}
                columns={[
                  { key: "end_date", label: "报告期", render: formatDate },
                  { key: "ann_date", label: "公告日", render: formatDate },
                  { key: "eps", label: "EPS", render: formatNum },
                  { key: "roe", label: "ROE", render: formatNum },
                  { key: "roa", label: "ROA", render: formatNum },
                  { key: "grossprofit_margin", label: "毛利率", render: formatNum },
                  { key: "debt_to_assets", label: "资产负债率", render: formatNum },
                ]}
              />
              <TableSection
                title="利润表"
                rows={financials?.income}
                columns={[
                  { key: "end_date", label: "报告期", render: formatDate },
                  { key: "ann_date", label: "公告日", render: formatDate },
                  { key: "revenue", label: "营业收入", render: formatNum },
                  { key: "operate_profit", label: "营业利润", render: formatNum },
                  { key: "total_profit", label: "利润总额", render: formatNum },
                  { key: "n_income", label: "净利润", render: formatNum },
                ]}
              />
              <TableSection
                title="资产负债表"
                rows={financials?.balance}
                columns={[
                  { key: "end_date", label: "报告期", render: formatDate },
                  { key: "total_assets", label: "总资产", render: formatNum },
                  { key: "total_liab", label: "总负债", render: formatNum },
                  { key: "total_hldr_eqy_exc_min_int", label: "归母权益", render: formatNum },
                  { key: "money_cap", label: "货币资金", render: formatNum },
                  { key: "inventories", label: "存货", render: formatNum },
                ]}
              />
              <TableSection
                title="现金流量表"
                rows={financials?.cashflow}
                columns={[
                  { key: "end_date", label: "报告期", render: formatDate },
                  { key: "n_cashflow_act", label: "经营现金流", render: formatNum },
                  { key: "n_cashflow_inv_act", label: "投资现金流", render: formatNum },
                  { key: "n_cash_flows_fnc_act", label: "融资现金流", render: formatNum },
                  { key: "n_incr_cash_cash_equ", label: "现金净增加额", render: formatNum },
                ]}
              />
              <TableSection
                title="分红送股"
                rows={dividends?.items}
                columns={[
                  { key: "end_date", label: "报告期", render: formatDate },
                  { key: "ann_date", label: "公告日", render: formatDate },
                  { key: "cash_div", label: "现金分红", render: formatNum },
                  { key: "stk_div", label: "送股", render: formatNum },
                  { key: "div_proc", label: "分红进度" },
                  { key: "ex_date", label: "除权除息日", render: formatDate },
                ]}
              />
            </div>
          </details>

          <details className="research-detail-card">
            <summary>股东与筹码明细</summary>
            <div className="research-detail-body">
              <TableSection
                title="股东人数"
                rows={holders?.holder_number}
                columns={[
                  { key: "ann_date", label: "公告日", render: formatDate },
                  { key: "end_date", label: "报告期", render: formatDate },
                  { key: "holder_num", label: "股东人数" },
                ]}
              />
              <TableSection
                title="前十大股东"
                rows={holders?.top10_holders}
                columns={[
                  { key: "end_date", label: "报告期", render: formatDate },
                  { key: "ann_date", label: "公告日", render: formatDate },
                  { key: "holder_name", label: "股东名称" },
                  { key: "hold_ratio", label: "持股比例", render: formatNum },
                  { key: "hold_amount", label: "持股数量", render: formatNum },
                ]}
              />
              <TableSection
                title="前十大流通股东"
                rows={holders?.top10_floatholders}
                columns={[
                  { key: "end_date", label: "报告期", render: formatDate },
                  { key: "ann_date", label: "公告日", render: formatDate },
                  { key: "holder_name", label: "股东名称" },
                  { key: "hold_ratio", label: "持股比例", render: formatNum },
                  { key: "hold_amount", label: "持股数量", render: formatNum },
                ]}
              />
              <TableSection
                title="筹码绩效"
                rows={chips?.cyq_perf}
                columns={[
                  { key: "trade_date", label: "交易日", render: formatDate },
                  { key: "weight_avg", label: "加权成本", render: formatNum },
                  { key: "cost_focus", label: "成本集中度", render: formatNum },
                  { key: "profit_ratio", label: "获利比例", render: formatNum },
                ]}
              />
              <TableSection
                title="筹码分布"
                rows={chips?.cyq_chips?.slice(0, 200)}
                columns={[
                  { key: "trade_date", label: "交易日", render: formatDate },
                  { key: "price", label: "价格", render: formatNum },
                  { key: "percent", label: "占比", render: formatNum },
                ]}
              />
            </div>
          </details>

          <details className="research-detail-card">
            <summary>资金流与跨境持股明细</summary>
            <div className="research-detail-body">
              <TableSection
                title="个股资金流"
                rows={flows?.moneyflow_dc}
                columns={[
                  { key: "trade_date", label: "交易日", render: formatDate },
                  { key: "net_mf_amount", label: "净流入额", render: formatNum },
                  { key: "buy_sm_amount", label: "小单买入", render: formatNum },
                  { key: "buy_md_amount", label: "中单买入", render: formatNum },
                  { key: "buy_lg_amount", label: "大单买入", render: formatNum },
                  { key: "buy_elg_amount", label: "特大单买入", render: formatNum },
                ]}
              />
              <TableSection
                title="融资融券明细"
                rows={flows?.margin_detail}
                columns={[
                  { key: "trade_date", label: "交易日", render: formatDate },
                  { key: "rzye", label: "融资余额", render: formatNum },
                  { key: "rqye", label: "融券余额", render: formatNum },
                  { key: "rzmre", label: "融资买入额", render: formatNum },
                  { key: "rzrqye", label: "两融余额", render: formatNum },
                ]}
              />
              <TableSection
                title="港股通持股"
                rows={flows?.hk_hold}
                columns={[
                  { key: "trade_date", label: "交易日", render: formatDate },
                  { key: "exchange", label: "市场" },
                  { key: "vol", label: "持股数量", render: formatNum },
                  { key: "ratio", label: "持股比例", render: formatNum },
                ]}
              />
              <TableSection
                title="CCASS 持股"
                rows={flows?.ccass_hold}
                columns={[
                  { key: "trade_date", label: "交易日", render: formatDate },
                  { key: "col_participant", label: "参与者" },
                  { key: "vol", label: "持股数量", render: formatNum },
                  { key: "hold_ratio", label: "持股比例", render: formatNum },
                ]}
              />
            </div>
          </details>

          <details className="research-detail-card">
            <summary>事件明细</summary>
            <div className="research-detail-body">
              <TableSection
                title="停复牌记录"
                rows={events?.suspend}
                columns={[
                  { key: "trade_date", label: "交易日", render: formatDate },
                  { key: "suspend_type", label: "停牌类型" },
                  { key: "suspend_timing", label: "停牌时段" },
                  { key: "reason", label: "原因" },
                ]}
              />
              <TableSection
                title="机构调研"
                rows={events?.institution_surveys}
                columns={[
                  { key: "surv_date", label: "调研日", render: formatDate },
                  { key: "rece_org", label: "接待机构" },
                  { key: "surv_type", label: "调研类型" },
                  { key: "title", label: "标题" },
                ]}
              />
            </div>
          </details>
        </div>
      </section>

      <section className="panel">
        <h2>OpenClaw 原始字段预览</h2>
        <p className="subtitle">当某些字段还没被拆成显式列时，OpenClaw 可以继续依赖 research API 返回的完整原始数组。</p>
        <div className="research-raw-preview">
          {Object.entries({
            overview,
            financials,
            dividends,
            holders,
            chips,
            flows,
            events,
          }).map(([key, value]) => (
            <details key={key} className="research-raw-item">
              <summary>{toLabel(key)}</summary>
              <pre>{JSON.stringify(value, null, 2)}</pre>
            </details>
          ))}
        </div>
      </section>
    </main>
  );
}
