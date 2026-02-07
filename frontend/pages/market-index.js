import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { apiFetch } from "../lib/api";

const INDEX_NAME_MAP = {
  "000001.SH": "上证指数",
  "399001.SZ": "深证成指",
  "399006.SZ": "创业板指",
  "000300.SH": "沪深300",
  "000905.SH": "中证500",
  "000852.SH": "中证1000",
  "000688.SH": "科创50",
};

const formatDate = (value) => {
  if (!value || String(value).length !== 8) return value || "-";
  const s = String(value);
  return `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}`;
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

const getChangeClass = (value) => {
  const num = Number(value);
  if (Number.isNaN(num)) return "change-flat";
  if (num > 0) return "change-up";
  if (num < 0) return "change-down";
  return "change-flat";
};

const getIndexName = (tsCode, apiName) => apiName || INDEX_NAME_MAP[tsCode] || tsCode;

const toNum = (value) => {
  if (value === null || value === undefined || value === "") return null;
  const num = Number(value);
  return Number.isFinite(num) ? num : null;
};

const formatChartValue = (value, digits = 4) => {
  if (value === null || value === undefined || value === "") return "-";
  const num = Number(value);
  if (Number.isNaN(num)) return "-";
  return num.toFixed(digits);
};

const buildChartOption = (rows) => {
  const sorted = [...rows].sort((a, b) => String(a.trade_date).localeCompare(String(b.trade_date)));
  const dates = sorted.map((item) => formatDate(item.trade_date));
  const candles = sorted.map((item) => [
    toNum(item.open) ?? 0,
    toNum(item.close) ?? 0,
    toNum(item.low) ?? 0,
    toNum(item.high) ?? 0,
  ]);

  const ma5 = sorted.map((item) => toNum(item.ma5));
  const ma10 = sorted.map((item) => toNum(item.ma10));
  const ma20 = sorted.map((item) => toNum(item.ma20));
  const ma60 = sorted.map((item) => toNum(item.ma60));

  const volumeBars = sorted.map((item) => {
    const open = toNum(item.open) ?? 0;
    const close = toNum(item.close) ?? 0;
    return {
      value: toNum(item.vol) ?? 0,
      itemStyle: { color: close >= open ? "#ef4444" : "#22c55e" },
    };
  });

  const macdDif = sorted.map((item) => toNum(item.macd_dif));
  const macdDea = sorted.map((item) => toNum(item.macd_dea));
  const macdBars = sorted.map((item) => {
    const value = toNum(item.macd);
    return {
      value,
      itemStyle: { color: (value ?? 0) >= 0 ? "#22c55e" : "#ef4444" },
    };
  });

  const kdjK = sorted.map((item) => toNum(item.kdj_k));
  const kdjD = sorted.map((item) => toNum(item.kdj_d));
  const kdjJ = sorted.map((item) => toNum(item.kdj_j));

  const rsi6 = sorted.map((item) => toNum(item.rsi6));
  const rsi12 = sorted.map((item) => toNum(item.rsi12));
  const rsi24 = sorted.map((item) => toNum(item.rsi24));

  const pe = sorted.map((item) => toNum(item.pe));
  const pb = sorted.map((item) => toNum(item.pb));

  const totalCount = sorted.length;
  const startIndex = Math.max(totalCount - 120, 0);
  const startPercent = totalCount > 1 ? (startIndex / (totalCount - 1)) * 100 : 0;

  return {
    backgroundColor: "#1a1a2e",
    animation: false,
    legend: {
      top: 6,
      left: 16,
      textStyle: { color: "#d2d2de" },
      itemWidth: 12,
      itemHeight: 8,
      data: [
        "K线",
        "MA5",
        "MA10",
        "MA20",
        "MA60",
        "成交量",
        "DIF",
        "DEA",
        "MACD柱",
        "K",
        "D",
        "J",
        "RSI6",
        "RSI12",
        "RSI24",
        "PE",
        "PB",
      ],
    },
    grid: [
      { left: 56, right: 48, top: 38, height: 300 },
      { left: 56, right: 48, top: 356, height: 80 },
      { left: 56, right: 48, top: 456, height: 140 },
      { left: 56, right: 48, top: 616, height: 140 },
      { left: 56, right: 48, top: 776, height: 140 },
      { left: 56, right: 48, top: 936, height: 140 },
    ],
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "cross" },
      formatter: (params) => {
        if (!params || params.length === 0) return "";
        const date = params[0].axisValue || "-";
        const lines = [`${date}`];
        params.forEach((item) => {
          if (item.seriesName === "K线") {
            const values = Array.isArray(item.value) ? item.value : [];
            lines.push(
              `开:${formatChartValue(values[0])} 收:${formatChartValue(values[1])} ` +
                `低:${formatChartValue(values[2])} 高:${formatChartValue(values[3])}`
            );
            return;
          }
          const value = item?.data?.value ?? item?.value;
          lines.push(`${item.seriesName}: ${formatChartValue(value)}`);
        });
        return lines.join("<br/>");
      },
    },
    axisPointer: {
      link: [{ xAxisIndex: [0, 1, 2, 3, 4, 5] }],
      label: { backgroundColor: "#505765" },
    },
    xAxis: [0, 1, 2, 3, 4, 5].map((gridIndex) => ({
      type: "category",
      gridIndex,
      data: dates,
      boundaryGap: true,
      axisLine: { lineStyle: { color: "#575767" } },
      axisLabel: {
        color: "#a7a7ba",
        show: gridIndex === 5,
      },
      axisTick: { show: false },
      splitLine: { show: false },
    })),
    yAxis: [
      {
        scale: true,
        axisLabel: { color: "#a7a7ba" },
        splitLine: { lineStyle: { color: "#303045" } },
      },
      {
        gridIndex: 1,
        scale: true,
        axisLabel: { color: "#a7a7ba" },
        splitLine: { show: false },
      },
      {
        gridIndex: 2,
        scale: true,
        axisLabel: { color: "#a7a7ba" },
        splitLine: { lineStyle: { color: "#303045" } },
      },
      {
        gridIndex: 3,
        min: 0,
        max: 100,
        axisLabel: { color: "#a7a7ba" },
        splitLine: { lineStyle: { color: "#303045" } },
      },
      {
        gridIndex: 4,
        min: 0,
        max: 100,
        axisLabel: { color: "#a7a7ba" },
        splitLine: { lineStyle: { color: "#303045" } },
      },
      {
        gridIndex: 5,
        scale: true,
        axisLabel: { color: "#f59e0b" },
        splitLine: { lineStyle: { color: "#303045" } },
      },
      {
        gridIndex: 5,
        scale: true,
        axisLabel: { color: "#06b6d4" },
        splitLine: { show: false },
      },
    ],
    dataZoom: [
      {
        type: "inside",
        xAxisIndex: [0, 1, 2, 3, 4, 5],
        start: startPercent,
        end: 100,
      },
      {
        type: "slider",
        xAxisIndex: [0, 1, 2, 3, 4, 5],
        start: startPercent,
        end: 100,
        height: 24,
        bottom: 12,
      },
    ],
    graphic: [
      { type: "text", left: 10, top: 460, style: { text: "MACD", fill: "#d2d2de", fontSize: 12 } },
      { type: "text", left: 10, top: 620, style: { text: "KDJ", fill: "#d2d2de", fontSize: 12 } },
      { type: "text", left: 10, top: 780, style: { text: "RSI", fill: "#d2d2de", fontSize: 12 } },
      { type: "text", left: 10, top: 940, style: { text: "PE/PB", fill: "#d2d2de", fontSize: 12 } },
    ],
    series: [
      {
        name: "K线",
        type: "candlestick",
        data: candles,
        itemStyle: {
          color: "#ef4444",
          color0: "#22c55e",
          borderColor: "#ef4444",
          borderColor0: "#22c55e",
        },
      },
      { name: "MA5", type: "line", data: ma5, symbol: "none", lineStyle: { width: 1, color: "#ffffff" } },
      { name: "MA10", type: "line", data: ma10, symbol: "none", lineStyle: { width: 1, color: "#ff69b4" } },
      { name: "MA20", type: "line", data: ma20, symbol: "none", lineStyle: { width: 1, color: "#ffff00" } },
      { name: "MA60", type: "line", data: ma60, symbol: "none", lineStyle: { width: 1, color: "#4169e1" } },
      { name: "成交量", type: "bar", xAxisIndex: 1, yAxisIndex: 1, data: volumeBars },
      { name: "DIF", type: "line", xAxisIndex: 2, yAxisIndex: 2, data: macdDif, symbol: "none", lineStyle: { width: 1, color: "#4169e1" } },
      { name: "DEA", type: "line", xAxisIndex: 2, yAxisIndex: 2, data: macdDea, symbol: "none", lineStyle: { width: 1, color: "#ff69b4" } },
      { name: "MACD柱", type: "bar", xAxisIndex: 2, yAxisIndex: 2, data: macdBars },
      {
        name: "K",
        type: "line",
        xAxisIndex: 3,
        yAxisIndex: 3,
        data: kdjK,
        symbol: "none",
        lineStyle: { width: 1, color: "#ff69b4" },
        markLine: {
          symbol: "none",
          silent: true,
          lineStyle: { color: "#575767", type: "dashed" },
          data: [{ yAxis: 20 }, { yAxis: 50 }, { yAxis: 80 }],
        },
      },
      { name: "D", type: "line", xAxisIndex: 3, yAxisIndex: 3, data: kdjD, symbol: "none", lineStyle: { width: 1, color: "#4169e1" } },
      { name: "J", type: "line", xAxisIndex: 3, yAxisIndex: 3, data: kdjJ, symbol: "none", lineStyle: { width: 1, color: "#ffff00" } },
      {
        name: "RSI6",
        type: "line",
        xAxisIndex: 4,
        yAxisIndex: 4,
        data: rsi6,
        symbol: "none",
        lineStyle: { width: 1, color: "#ff69b4" },
        markLine: {
          symbol: "none",
          silent: true,
          lineStyle: { color: "#575767", type: "dashed" },
          data: [{ yAxis: 30 }, { yAxis: 70 }],
        },
      },
      { name: "RSI12", type: "line", xAxisIndex: 4, yAxisIndex: 4, data: rsi12, symbol: "none", lineStyle: { width: 1, color: "#4169e1" } },
      { name: "RSI24", type: "line", xAxisIndex: 4, yAxisIndex: 4, data: rsi24, symbol: "none", lineStyle: { width: 1, color: "#ffff00" } },
      { name: "PE", type: "line", xAxisIndex: 5, yAxisIndex: 5, data: pe, symbol: "none", lineStyle: { width: 1.2, color: "#f59e0b" } },
      { name: "PB", type: "line", xAxisIndex: 5, yAxisIndex: 6, data: pb, symbol: "none", lineStyle: { width: 1.2, color: "#06b6d4" } },
    ],
  };
};

export default function MarketIndexPage() {
  const chartRef = useRef(null);
  const chartInstanceRef = useRef(null);

  const [overview, setOverview] = useState([]);
  const [selectedCode, setSelectedCode] = useState("000300.SH");
  const [chartRows, setChartRows] = useState([]);
  const [activeTradeDate, setActiveTradeDate] = useState("");
  const [loading, setLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState("");

  const setChartEl = useCallback((el) => {
    chartRef.current = el;
  }, []);

  const loadOverview = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await apiFetch("/market-index/overview");
      if (!res.ok) throw new Error(`加载失败: ${res.status}`);
      const data = await res.json();
      const items = data.items || [];
      setOverview(items);
      if (items.length > 0) {
        setSelectedCode((current) =>
          items.find((item) => item.ts_code === current) ? current : items[0].ts_code
        );
      }
    } catch (err) {
      setOverview([]);
      setError(err.message || "加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  const loadDetail = useCallback(async () => {
    if (!selectedCode) return;
    setDetailLoading(true);
    try {
      const chartParams = new URLSearchParams();
      chartParams.set("ts_code", selectedCode);
      chartParams.set("limit", "500");

      const chartRes = await apiFetch(`/market-index/chart?${chartParams.toString()}`);
      if (!chartRes.ok) throw new Error(`图表加载失败: ${chartRes.status}`);

      const chartData = await chartRes.json();
      const chartItems = chartData.items || [];

      setChartRows(chartItems);
      if (chartItems.length > 0) {
        const latest = [...chartItems].sort((a, b) => String(b.trade_date).localeCompare(String(a.trade_date)))[0];
        setActiveTradeDate(latest?.trade_date || "");
      } else {
        setActiveTradeDate("");
      }
    } catch (err) {
      setChartRows([]);
      setActiveTradeDate("");
      setError(err.message || "加载失败");
    } finally {
      setDetailLoading(false);
    }
  }, [selectedCode]);

  useEffect(() => {
    loadOverview();
  }, [loadOverview]);

  useEffect(() => {
    loadDetail();
  }, [loadDetail]);

  useEffect(() => {
    let mounted = true;

    const renderChart = async () => {
      if (!chartRef.current || chartRows.length === 0) return;
      const echartsModule = await import("echarts");
      const echarts = echartsModule?.default ?? echartsModule;
      if (!mounted || !chartRef.current || !echarts?.init) return;

      if (!chartInstanceRef.current) {
        chartInstanceRef.current = echarts.init(chartRef.current, null, { renderer: "canvas" });
      }

      const option = buildChartOption(chartRows);
      chartInstanceRef.current.setOption(option, { notMerge: true });
      requestAnimationFrame(() => chartInstanceRef.current?.resize());
    };

    renderChart().catch((err) => {
      if (mounted) {
        setError((prev) => prev || err?.message || "图表渲染失败");
      }
    });

    return () => {
      mounted = false;
    };
  }, [chartRows]);

  useEffect(() => {
    if (!chartInstanceRef.current || !activeTradeDate || chartRows.length === 0) return;
    const sorted = [...chartRows].sort((a, b) => String(a.trade_date).localeCompare(String(b.trade_date)));
    const idx = sorted.findIndex((item) => String(item.trade_date) === String(activeTradeDate));
    if (idx < 0) return;
    chartInstanceRef.current.dispatchAction({ type: "showTip", seriesIndex: 0, dataIndex: idx });
  }, [activeTradeDate, chartRows]);

  useEffect(() => {
    const onResize = () => chartInstanceRef.current?.resize();
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  useEffect(() => {
    return () => {
      if (chartInstanceRef.current) {
        chartInstanceRef.current.dispose();
        chartInstanceRef.current = null;
      }
    };
  }, []);

  const selectedOverview = useMemo(
    () => overview.find((item) => item.ts_code === selectedCode) || null,
    [overview, selectedCode]
  );
  const selectedName = getIndexName(selectedCode, selectedOverview?.ts_name);

  return (
    <main className="page market-index-page">
      <header className="header">
        <div>
          <p className="eyebrow">Quant Platform</p>
          <h1>大盘指数</h1>
          <p className="subtitle">指数估值与技术因子监控</p>
        </div>
      </header>

      {error ? <div className="error">{error}</div> : null}

      <section className="market-overview-grid">
        {loading ? (
          <div className="table-wrap">
            <div className="loading-container">
              <div className="spinner"></div>
              <p>加载概览中...</p>
            </div>
          </div>
        ) : overview.length === 0 ? (
          <div className="table-wrap">
            <div className="empty">暂无指数概览数据</div>
          </div>
        ) : (
          overview.map((item) => (
            <button
              type="button"
              key={item.ts_code}
              className={`market-card ${selectedCode === item.ts_code ? "active" : ""}`}
              onClick={() => setSelectedCode(item.ts_code)}
            >
              <div className="market-card-head">
                <span className="market-card-code">
                  {item.ts_code} {getIndexName(item.ts_code, item.ts_name)}
                </span>
              </div>
              <div className={`change-pill ${getChangeClass(item.pct_change)}`}>
                {formatPct(item.pct_change)}
              </div>
              <div className="market-card-metrics">
                <span>PE {formatNum(item.pe)}</span>
                <span>PB {formatNum(item.pb)}</span>
                <span>换手 {formatNum(item.turnover_rate)}%</span>
              </div>
            </button>
          ))
        )}
      </section>

      <section className="table-wrap">
        <div className="avg-panel-header">{selectedCode} {selectedName} K 线与技术指标</div>
        {detailLoading ? (
          <div className="loading-container">
            <div className="spinner"></div>
            <p>加载图表中...</p>
          </div>
        ) : chartRows.length === 0 ? (
          <div className="empty">暂无图表数据</div>
        ) : (
          <div className="market-chart-container" ref={setChartEl} />
        )}
      </section>

      <section className="table-wrap indicator-guide">
        <div className="avg-panel-header">技术指标说明</div>
        <div className="indicator-guide-content">
          <div className="indicator-item">
            <h3>📊 MACD (指数平滑异同移动平均线)</h3>
            <ul>
              <li><strong>金叉看涨</strong>：DIF 线上穿 DEA 线，MACD 柱由绿转红 → 买入信号</li>
              <li><strong>死叉看跌</strong>：DIF 线下穿 DEA 线，MACD 柱由红转绿 → 卖出信号</li>
              <li><strong>柱状图</strong>：红柱越长动能越强（上涨），绿柱越长动能越强（下跌）</li>
              <li><strong>背离</strong>：价格创新高但 MACD 未创新高 → 顶背离，警惕回调</li>
            </ul>
          </div>

          <div className="indicator-item">
            <h3>📈 KDJ (随机指标)</h3>
            <ul>
              <li><strong>超买区</strong>：K、D 值 &gt; 80 → 超买，警惕回调，考虑卖出</li>
              <li><strong>超卖区</strong>：K、D 值 &lt; 20 → 超卖，可能反弹，考虑买入</li>
              <li><strong>金叉看涨</strong>：K 线上穿 D 线 → 买入信号（低位金叉更可靠）</li>
              <li><strong>死叉看跌</strong>：K 线下穿 D 线 → 卖出信号（高位死叉更可靠）</li>
              <li><strong>J 值</strong>：J &gt; 100 严重超买，J &lt; 0 严重超卖，反应更敏感</li>
            </ul>
          </div>

          <div className="indicator-item">
            <h3>💹 RSI (相对强弱指标)</h3>
            <ul>
              <li><strong>超买区</strong>：RSI &gt; 70 → 超买，警惕回调</li>
              <li><strong>超卖区</strong>：RSI &lt; 30 → 超卖，可能反弹</li>
              <li><strong>强势区间</strong>：RSI 在 50-70 之间震荡 → 上升趋势良好</li>
              <li><strong>弱势区间</strong>：RSI 在 30-50 之间震荡 → 下降趋势</li>
              <li><strong>背离</strong>：价格创新高但 RSI 未创新高 → 顶背离，警惕风险</li>
            </ul>
          </div>

          <div className="indicator-item">
            <h3>💰 PE/PB (估值指标)</h3>
            <ul>
              <li><strong>PE (市盈率)</strong>：市值 ÷ 净利润，反映盈利能力估值</li>
              <li className="indent">• PE 越低 → 相对低估，但需结合行业均值判断</li>
              <li className="indent">• PE 过高 → 可能高估，泡沫风险</li>
              <li className="indent">• PE &lt; 0 表示公司亏损</li>
              <li><strong>PB (市净率)</strong>：市值 ÷ 净资产，反映资产估值</li>
              <li className="indent">• PB &lt; 1 → 股价低于净资产，可能低估</li>
              <li className="indent">• PB 越低 → 安全边际越高</li>
              <li><strong>综合判断</strong>：PE/PB 历史低位 + 技术指标超卖 → 长期布局机会</li>
            </ul>
          </div>

          <div className="indicator-item">
            <h3>⚠️ 使用提示</h3>
            <ul>
              <li><strong>多指标结合</strong>：单一指标可能失效，建议结合多个指标共同判断</li>
              <li><strong>趋势优先</strong>：技术指标在趋势中更可靠，震荡市容易发出虚假信号</li>
              <li><strong>周期匹配</strong>：短线看 RSI6/KDJ，中线看 MACD/RSI12，长线看 PE/PB 估值</li>
              <li><strong>风险控制</strong>：技术指标是辅助工具，不是圣杯，务必设置止损</li>
            </ul>
          </div>
        </div>
      </section>
    </main>
  );
}
