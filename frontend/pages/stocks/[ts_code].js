import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/router";
import Link from "next/link";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:9000/api";

const formatDate = (value) => {
  if (!value || value.length !== 8) {
    return value || "";
  }
  return `${value.slice(0, 4)}-${value.slice(4, 6)}-${value.slice(6, 8)}`;
};

export default function StockKline() {
  const router = useRouter();
  const { ts_code: tsCode } = router.query;
  const chartRef = useRef(null);
  const chartInstanceRef = useRef(null);

  const [daily, setDaily] = useState([]);
  const [adjFactor, setAdjFactor] = useState([]);
  const [stockInfo, setStockInfo] = useState(null);
  const [features, setFeatures] = useState([]);
  const [adjPage, setAdjPage] = useState(1);
  const [adjPageSize] = useState(10);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const adjMap = useMemo(() => {
    const map = new Map();
    adjFactor.forEach((item) => {
      map.set(item.trade_date, item.adj_factor);
    });
    return map;
  }, [adjFactor]);

  const sortedDaily = useMemo(() => {
    if (!daily.length) {
      return [];
    }
    return [...daily].sort(
      (a, b) => Number(a.trade_date) - Number(b.trade_date)
    );
  }, [daily]);

  const displayAdj = useMemo(() => {
    return sortedDaily.slice(-120).map((item) => ({
      trade_date: item.trade_date,
      adj_factor: adjMap.get(item.trade_date) ?? null,
    }));
  }, [sortedDaily, adjMap]);

  const featureMap = useMemo(() => {
    const map = new Map();
    features.forEach((item) => {
      map.set(item.trade_date, item);
    });
    return map;
  }, [features]);

  const adjTotalPages = Math.max(Math.ceil(displayAdj.length / adjPageSize), 1);
  const adjSlice = useMemo(() => {
    const start = (adjPage - 1) * adjPageSize;
    return displayAdj.slice(start, start + adjPageSize);
  }, [displayAdj, adjPage, adjPageSize]);

  const fetchData = async () => {
    if (!tsCode) {
      return;
    }
    setLoading(true);
    setError("");
    try {
      const [candlesRes, basicRes, featuresRes] = await Promise.all([
        fetch(`${API_BASE}/stocks/${tsCode}/candles`),
        fetch(`${API_BASE}/stocks/${tsCode}/basic`),
        fetch(`${API_BASE}/stocks/${tsCode}/features`),
      ]);
      if (!candlesRes.ok) {
        throw new Error(`加载失败: ${candlesRes.status}`);
      }
      const data = await candlesRes.json();
      setDaily(data.daily || []);
      setAdjFactor(data.adj_factor || []);
      if (basicRes.ok) {
        const info = await basicRes.json();
        setStockInfo(info);
      }
      if (featuresRes.ok) {
        const featureData = await featuresRes.json();
        setFeatures(featureData.items || []);
      }
    } catch (err) {
      setError(err.message || "加载失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [tsCode]);

  useEffect(() => {
    setAdjPage(1);
  }, [displayAdj.length]);

  useEffect(() => {
    let mounted = true;

    const renderChart = async () => {
      if (!chartRef.current || sortedDaily.length === 0) {
        return;
      }
      const echarts = await import("echarts");
      if (!mounted) {
        return;
      }
      if (!chartInstanceRef.current) {
        chartInstanceRef.current = echarts.init(chartRef.current);
      }

      const dates = sortedDaily.map((item) => formatDate(item.trade_date));
      const candles = sortedDaily.map((item) => [
        Number(item.open),
        Number(item.close),
        Number(item.low),
        Number(item.high),
      ]);
      const volumes = sortedDaily.map((item) => Number(item.vol) || 0);
      const volumeBars = sortedDaily.map((item) => ({
        value: item.vol || 0,
        itemStyle: {
          color: (item.close ?? 0) >= (item.open ?? 0) ? "#ef4444" : "#22c55e",
        },
      }));
      const totalCount = sortedDaily.length;
      const startIndex = Math.max(totalCount - 120, 0);
      const startPercent = totalCount > 1 ? (startIndex / (totalCount - 1)) * 100 : 0;

      const maSeries = (key) =>
        sortedDaily.map((item) => featureMap.get(item.trade_date)?.[key] ?? null);

      const macdDif = sortedDaily.map(
        (item) => featureMap.get(item.trade_date)?.macd_dif ?? null
      );
      const macdDea = sortedDaily.map(
        (item) => featureMap.get(item.trade_date)?.macd_dea ?? null
      );
      const macdHist = sortedDaily.map(
        (item) => featureMap.get(item.trade_date)?.macd_hist ?? null
      );
      const kdjK = sortedDaily.map(
        (item) => featureMap.get(item.trade_date)?.kdj_k ?? null
      );
      const kdjD = sortedDaily.map(
        (item) => featureMap.get(item.trade_date)?.kdj_d ?? null
      );
      const kdjJ = sortedDaily.map(
        (item) => featureMap.get(item.trade_date)?.kdj_j ?? null
      );
      const rsi14 = sortedDaily.map(
        (item) => featureMap.get(item.trade_date)?.rsi_14 ?? null
      );
      const bollMid = sortedDaily.map(
        (item) => featureMap.get(item.trade_date)?.boll_mid ?? null
      );
      const bollUpper = sortedDaily.map(
        (item) => featureMap.get(item.trade_date)?.boll_upper ?? null
      );
      const bollLower = sortedDaily.map(
        (item) => featureMap.get(item.trade_date)?.boll_lower ?? null
      );

      chartInstanceRef.current.setOption({
        backgroundColor: "transparent",
        grid: [
          { left: 40, right: 20, top: 20, height: "42%" },
          { left: 40, right: 20, top: "50%", height: "10%" },
          { left: 40, right: 20, top: "62%", height: "10%" },
          { left: 40, right: 20, top: "74%", height: "10%" },
          { left: 40, right: 20, top: "86%", height: "10%" },
          { left: 40, right: 20, top: "98%", height: "10%" },
        ],
        tooltip: {
          trigger: "axis",
          formatter: (params) => {
            const candle = params.find((item) => item.seriesType === "candlestick");
            if (!candle) {
              return "";
            }
            const index = candle.dataIndex;
            const date = dates[index];
            const values = candle.data || [];
            const adjValue = displayAdj[index]?.adj_factor;
            const volumeValue = volumes[index];
            return [
              `${date}`,
              `开盘: ${values[0]}`,
              `收盘: ${values[1]}`,
              `最低: ${values[2]}`,
              `最高: ${values[3]}`,
              `成交量: ${volumeValue ?? "-"}`,
              `复权因子: ${adjValue ?? "-"}`,
            ].join("<br/>");
          },
        },
        axisPointer: { link: [{ xAxisIndex: [0, 1, 2, 3, 4, 5] }] },
        xAxis: [
          {
            type: "category",
            data: dates,
            boundaryGap: true,
            axisLine: { lineStyle: { color: "#c6c6c6" } },
            axisLabel: { color: "#6c6c6c" },
          },
          {
            type: "category",
            data: dates,
            gridIndex: 1,
            boundaryGap: true,
            axisLine: { lineStyle: { color: "#c6c6c6" } },
            axisLabel: { color: "#6c6c6c" },
          },
          {
            type: "category",
            data: dates,
            gridIndex: 2,
            boundaryGap: true,
            axisLine: { lineStyle: { color: "#c6c6c6" } },
            axisLabel: { show: false },
          },
          {
            type: "category",
            data: dates,
            gridIndex: 3,
            boundaryGap: true,
            axisLine: { lineStyle: { color: "#c6c6c6" } },
            axisLabel: { show: false },
          },
          {
            type: "category",
            data: dates,
            gridIndex: 4,
            boundaryGap: true,
            axisLine: { lineStyle: { color: "#c6c6c6" } },
            axisLabel: { show: false },
          },
          {
            type: "category",
            data: dates,
            gridIndex: 5,
            boundaryGap: true,
            axisLine: { lineStyle: { color: "#c6c6c6" } },
            axisLabel: { show: false },
          },
        ],
        yAxis: [
          {
            scale: true,
            axisLabel: { color: "#6c6c6c" },
            splitLine: { lineStyle: { color: "#eee" } },
          },
          {
            gridIndex: 1,
            axisLabel: { color: "#6c6c6c" },
            splitLine: { show: false },
          },
          {
            gridIndex: 2,
            axisLabel: { color: "#6c6c6c" },
            splitLine: { show: false },
          },
          {
            gridIndex: 3,
            axisLabel: { color: "#6c6c6c" },
            splitLine: { show: false },
          },
          {
            gridIndex: 4,
            axisLabel: { color: "#6c6c6c" },
            splitLine: { show: false },
          },
          {
            gridIndex: 5,
            axisLabel: { color: "#6c6c6c" },
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
            top: "114%",
            height: 18,
          },
        ],
        series: [
          {
            name: "K线",
            type: "candlestick",
            xAxisIndex: 0,
            yAxisIndex: 0,
            data: candles,
            barWidth: "60%",
            z: 3,
            itemStyle: {
              color: "#ef4444",
              color0: "#22c55e",
              borderColor: "#ef4444",
              borderColor0: "#22c55e",
            },
          },
          {
            name: "MA5",
            type: "line",
            xAxisIndex: 0,
            yAxisIndex: 0,
            data: maSeries("ma_5"),
            showSymbol: false,
            lineStyle: { color: "#ffffff", width: 1.5 },
          },
          {
            name: "MA10",
            type: "line",
            xAxisIndex: 0,
            yAxisIndex: 0,
            data: maSeries("ma_10"),
            showSymbol: false,
            lineStyle: { color: "#a855f7", width: 1.5 },
          },
          {
            name: "MA20",
            type: "line",
            xAxisIndex: 0,
            yAxisIndex: 0,
            data: maSeries("ma_20"),
            showSymbol: false,
            lineStyle: { color: "#facc15", width: 1.5 },
          },
          {
            name: "MA30",
            type: "line",
            xAxisIndex: 0,
            yAxisIndex: 0,
            data: maSeries("ma_30"),
            showSymbol: false,
            lineStyle: { color: "#3b82f6", width: 1.5 },
          },
          {
            name: "成交量",
            type: "bar",
            xAxisIndex: 1,
            yAxisIndex: 1,
            data: volumeBars,
            barWidth: "60%",
          },
          {
            name: "MACD",
            type: "bar",
            xAxisIndex: 2,
            yAxisIndex: 2,
            data: macdHist,
            itemStyle: { color: "#94a3b8" },
          },
          {
            name: "DIF",
            type: "line",
            xAxisIndex: 2,
            yAxisIndex: 2,
            data: macdDif,
            showSymbol: false,
            lineStyle: { color: "#f97316", width: 1.2 },
          },
          {
            name: "DEA",
            type: "line",
            xAxisIndex: 2,
            yAxisIndex: 2,
            data: macdDea,
            showSymbol: false,
            lineStyle: { color: "#0ea5e9", width: 1.2 },
          },
          {
            name: "KDJ-K",
            type: "line",
            xAxisIndex: 3,
            yAxisIndex: 3,
            data: kdjK,
            showSymbol: false,
            lineStyle: { color: "#f97316", width: 1.2 },
          },
          {
            name: "KDJ-D",
            type: "line",
            xAxisIndex: 3,
            yAxisIndex: 3,
            data: kdjD,
            showSymbol: false,
            lineStyle: { color: "#0ea5e9", width: 1.2 },
          },
          {
            name: "KDJ-J",
            type: "line",
            xAxisIndex: 3,
            yAxisIndex: 3,
            data: kdjJ,
            showSymbol: false,
            lineStyle: { color: "#a855f7", width: 1.2 },
          },
          {
            name: "RSI",
            type: "line",
            xAxisIndex: 4,
            yAxisIndex: 4,
            data: rsi14,
            showSymbol: false,
            lineStyle: { color: "#22c55e", width: 1.2 },
          },
          {
            name: "BOLL-MID",
            type: "line",
            xAxisIndex: 5,
            yAxisIndex: 5,
            data: bollMid,
            showSymbol: false,
            lineStyle: { color: "#eab308", width: 1.2 },
          },
          {
            name: "BOLL-UPPER",
            type: "line",
            xAxisIndex: 5,
            yAxisIndex: 5,
            data: bollUpper,
            showSymbol: false,
            lineStyle: { color: "#ef4444", width: 1.2 },
          },
          {
            name: "BOLL-LOWER",
            type: "line",
            xAxisIndex: 5,
            yAxisIndex: 5,
            data: bollLower,
            showSymbol: false,
            lineStyle: { color: "#3b82f6", width: 1.2 },
          },
        ],
      });
    };

    renderChart();

    return () => {
      mounted = false;
    };
  }, [sortedDaily, displayAdj, adjMap, featureMap]);

  useEffect(() => {
    return () => {
      if (chartInstanceRef.current) {
        chartInstanceRef.current.dispose();
        chartInstanceRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    const handleResize = () => {
      if (chartInstanceRef.current) {
        chartInstanceRef.current.resize();
      }
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  return (
    <main className="page">
      <header className="header">
        <div>
          <p className="eyebrow">Quant Platform</p>
          <h1>
            {tsCode
              ? [
                  tsCode,
                  stockInfo?.name,
                  stockInfo?.industry,
                  stockInfo?.market,
                  "K线",
                ]
                  .filter(Boolean)
                  .join(" · ")
              : "K线"}
          </h1>
          <p className="subtitle">日线数据来自 DuckDB</p>
        </div>
        <Link className="primary" href="/">
          返回列表
        </Link>
      </header>

      {error ? <div className="error">{error}</div> : null}

      <section className="table-wrap">
        {loading ? (
          <div className="loading-container">
            <div className="spinner"></div>
            <p>加载中...</p>
          </div>
        ) : sortedDaily.length === 0 ? (
          <div className="empty-state">
            <span className="empty-icon">📉</span>
            <p>暂无K线数据</p>
            <small>请先拉取该股票日线数据</small>
          </div>
        ) : (
          <>
            <div className="chart-canvas" ref={chartRef} />
            <div className="adj-table">
              <h3>复权因子（最近120天）</h3>
              <table>
                <thead>
                  <tr>
                    <th>日期</th>
                    <th>复权因子</th>
                  </tr>
                </thead>
                <tbody>
                  {adjSlice.map((item) => (
                    <tr key={item.trade_date}>
                      <td>{formatDate(item.trade_date)}</td>
                      <td>{item.adj_factor ?? "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="pagination">
                <span>
                  共 {displayAdj.length} 条，第 {adjPage} / {adjTotalPages} 页
                </span>
                <div className="pager-actions">
                  <button
                    type="button"
                    onClick={() => setAdjPage((current) => Math.max(current - 1, 1))}
                    disabled={adjPage <= 1}
                  >
                    上一页
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      setAdjPage((current) => Math.min(current + 1, adjTotalPages))
                    }
                    disabled={adjPage >= adjTotalPages}
                  >
                    下一页
                  </button>
                </div>
              </div>
            </div>
          </>
        )}
      </section>
    </main>
  );
}
