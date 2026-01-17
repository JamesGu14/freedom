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

const normalizeDailyRows = (rows) => {
  const map = new Map();
  rows.forEach((row) => {
    if (!row?.trade_date) {
      return;
    }
    map.set(row.trade_date, row);
  });
  return Array.from(map.values());
};

const normalizeAdjRows = (rows) => {
  const map = new Map();
  rows.forEach((row) => {
    if (!row?.trade_date) {
      return;
    }
    map.set(row.trade_date, row);
  });
  return Array.from(map.values());
};

export default function StockKline() {
  const router = useRouter();
  const { ts_code: tsCode } = router.query;
  const chartRef = useRef(null);
  const chartInstanceRef = useRef(null);

  const [daily, setDaily] = useState([]);
  const [adjFactor, setAdjFactor] = useState([]);
  const [indicators, setIndicators] = useState([]);
  const [stockInfo, setStockInfo] = useState(null);
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
      setDaily(normalizeDailyRows(data.daily || []));
      setAdjFactor(normalizeAdjRows(data.adj_factor || []));
      if (basicRes.ok) {
        const info = await basicRes.json();
        setStockInfo(info);
      }
      if (featuresRes.ok) {
        const featuresData = await featuresRes.json();
        setIndicators(featuresData.indicators || []);
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
        item.open,
        item.close,
        item.low,
        item.high,
      ]);
      const volumes = sortedDaily.map((item) => item.vol || 0);

      // Create indicator map for quick lookup
      const indicatorMap = new Map();
      indicators.forEach((ind) => {
        if (ind.trade_date) {
          indicatorMap.set(ind.trade_date, ind);
        }
      });

      // Get MA values aligned with daily data
      const ma5Values = sortedDaily.map((item) => {
        const ind = indicatorMap.get(item.trade_date);
        return ind?.ma5 ?? null;
      });
      const ma10Values = sortedDaily.map((item) => {
        const ind = indicatorMap.get(item.trade_date);
        return ind?.ma10 ?? null;
      });
      const ma20Values = sortedDaily.map((item) => {
        const ind = indicatorMap.get(item.trade_date);
        return ind?.ma20 ?? null;
      });
      const ma30Values = sortedDaily.map((item) => {
        const ind = indicatorMap.get(item.trade_date);
        return ind?.ma30 ?? null;
      });
      // Get KDJ values
      const kdjKValues = sortedDaily.map((item) => {
        const ind = indicatorMap.get(item.trade_date);
        return ind?.kdj_k ?? null;
      });
      const kdjDValues = sortedDaily.map((item) => {
        const ind = indicatorMap.get(item.trade_date);
        return ind?.kdj_d ?? null;
      });
      const kdjJValues = sortedDaily.map((item) => {
        const ind = indicatorMap.get(item.trade_date);
        return ind?.kdj_j ?? null;
      });
      // Get MACD values
      const macdValues = sortedDaily.map((item) => {
        const ind = indicatorMap.get(item.trade_date);
        return ind?.macd ?? null;
      });
      const macdSignalValues = sortedDaily.map((item) => {
        const ind = indicatorMap.get(item.trade_date);
        return ind?.macd_signal ?? null;
      });
      const macdHistValues = sortedDaily.map((item) => {
        const ind = indicatorMap.get(item.trade_date);
        return ind?.macd_hist ?? null;
      });
      const volumeBars = sortedDaily.map((item) => ({
        value: item.vol || 0,
        itemStyle: {
          color: (item.close ?? 0) >= (item.open ?? 0) ? "#ef4444" : "#22c55e",
        },
      }));
      const totalCount = sortedDaily.length;
      const startIndex = Math.max(totalCount - 120, 0);
      const startPercent = totalCount > 1 ? (startIndex / (totalCount - 1)) * 100 : 0;

      chartInstanceRef.current.setOption({
        backgroundColor: "#000000",
        grid: [
          { left: 40, right: 20, top: 30, height: 280 },
          { left: 40, right: 20, top: 330, height: 90 },
          { left: 40, right: 20, top: 450, height: 180 },
          { left: 40, right: 20, top: 660, height: 180 },
        ],
        tooltip: {
          trigger: "axis",
          formatter: (params) => {
            if (!params || params.length === 0) {
              return "";
            }
            const formatNumber = (val) => {
              if (val == null || val === "") return "-";
              const num = typeof val === "number" ? val : parseFloat(val);
              return isNaN(num) ? "-" : num.toFixed(4);
            };
            const index = params[0].dataIndex;
            const date = dates[index];
            const lines = [`${date}`];

            // K线数据 - 从原始数据读取，确保准确性
            if (index >= 0 && index < sortedDaily.length) {
              const item = sortedDaily[index];
              lines.push(
                `开盘: ${formatNumber(item.open)}`,
                `收盘: ${formatNumber(item.close)}`,
                `最低: ${formatNumber(item.low)}`,
                `最高: ${formatNumber(item.high)}`
              );
            }

            // MA数据
            const ma5 = params.find((item) => item.seriesName === "MA5");
            const ma10 = params.find((item) => item.seriesName === "MA10");
            const ma20 = params.find((item) => item.seriesName === "MA20");
            const ma30 = params.find((item) => item.seriesName === "MA30");
            if (ma5 || ma10 || ma20 || ma30) {
              lines.push("");
              if (ma5) lines.push(`MA5: ${formatNumber(ma5.value)}`);
              if (ma10) lines.push(`MA10: ${formatNumber(ma10.value)}`);
              if (ma20) lines.push(`MA20: ${formatNumber(ma20.value)}`);
              if (ma30) lines.push(`MA30: ${formatNumber(ma30.value)}`);
            }

            // 成交量
            const volume = params.find((item) => item.seriesName === "成交量");
            if (volume) {
              lines.push(`成交量: ${formatNumber(volume.value)}`);
            }

            // KDJ数据
            const kdjK = params.find((item) => item.seriesName === "KDJ-K");
            const kdjD = params.find((item) => item.seriesName === "KDJ-D");
            const kdjJ = params.find((item) => item.seriesName === "KDJ-J");
            if (kdjK || kdjD || kdjJ) {
              lines.push("");
              if (kdjK) lines.push(`KDJ-K: ${formatNumber(kdjK.value)}`);
              if (kdjD) lines.push(`KDJ-D: ${formatNumber(kdjD.value)}`);
              if (kdjJ) lines.push(`KDJ-J: ${formatNumber(kdjJ.value)}`);
            }

            // MACD数据
            const macd = params.find((item) => item.seriesName === "MACD");
            const macdSignal = params.find((item) => item.seriesName === "MACD-Signal");
            const macdHist = params.find((item) => item.seriesName === "MACD-Hist");
            if (macd || macdSignal || macdHist) {
              lines.push("");
              if (macd) lines.push(`MACD: ${formatNumber(macd.value)}`);
              if (macdSignal) lines.push(`MACD-Signal: ${formatNumber(macdSignal.value)}`);
              if (macdHist) lines.push(`MACD-Hist: ${formatNumber(macdHist.value)}`);
            }

            return lines.join("<br/>");
          },
        },
        axisPointer: { link: [{ xAxisIndex: [0, 1, 2, 3] }] },
        xAxis: [
          {
            type: "category",
            data: dates,
            boundaryGap: true,
            axisLine: { lineStyle: { color: "#666666" } },
            axisLabel: { color: "#999999" },
          },
          {
            type: "category",
            data: dates,
            gridIndex: 1,
            boundaryGap: true,
            axisLine: { lineStyle: { color: "#666666" } },
            axisLabel: { color: "#999999" },
          },
          {
            type: "category",
            data: dates,
            gridIndex: 2,
            boundaryGap: true,
            axisLine: { lineStyle: { color: "#666666" } },
            axisLabel: { color: "#999999" },
          },
          {
            type: "category",
            data: dates,
            gridIndex: 3,
            boundaryGap: true,
            axisLine: { lineStyle: { color: "#666666" } },
            axisLabel: { color: "#999999" },
          },
        ],
        yAxis: [
          {
            scale: true,
            axisLabel: { color: "#999999" },
            splitLine: { lineStyle: { color: "#333333" } },
          },
          {
            gridIndex: 1,
            axisLabel: { color: "#999999" },
            splitLine: { show: false },
          },
          {
            gridIndex: 2,
            axisLabel: { color: "#999999" },
            splitLine: { lineStyle: { color: "#333333" } },
          },
          {
            gridIndex: 3,
            axisLabel: { color: "#999999" },
            splitLine: { lineStyle: { color: "#333333" } },
          },
        ],
        dataZoom: [
          {
            type: "inside",
            xAxisIndex: [0, 1, 2, 3],
            start: startPercent,
            end: 100,
          },
          {
            type: "slider",
            xAxisIndex: [0, 1, 2, 3],
            start: startPercent,
            end: 100,
            bottom: 10,
            height: 25,
          },
        ],
        graphic: [
          {
            type: "text",
            left: 50,
            top: 452,
            style: {
              text: "KDJ",
              fontSize: 14,
              fontWeight: "bold",
              fill: "#ffffff",
            },
          },
          {
            type: "text",
            left: 50,
            top: 662,
            style: {
              text: "MACD",
              fontSize: 14,
              fontWeight: "bold",
              fill: "#ffffff",
            },
          },
        ],
        series: [
          {
            name: "K线",
            type: "candlestick",
            data: candles,
            barCategoryGap: "10%",
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
            data: ma5Values,
            smooth: false,
            lineStyle: {
              color: "#ffffff",
              width: 1,
            },
            symbol: "none",
          },
          {
            name: "MA10",
            type: "line",
            data: ma10Values,
            smooth: false,
            lineStyle: {
              color: "#ff69b4",
              width: 1,
            },
            symbol: "none",
          },
          {
            name: "MA20",
            type: "line",
            data: ma20Values,
            smooth: false,
            lineStyle: {
              color: "#ffff00",
              width: 1,
            },
            symbol: "none",
          },
          {
            name: "MA30",
            type: "line",
            data: ma30Values,
            smooth: false,
            lineStyle: {
              color: "#4169e1",
              width: 1,
            },
            symbol: "none",
          },
          {
            name: "成交量",
            type: "bar",
            xAxisIndex: 1,
            yAxisIndex: 1,
            data: volumeBars,
          },
          // KDJ指标
          {
            name: "KDJ-K",
            type: "line",
            xAxisIndex: 2,
            yAxisIndex: 2,
            data: kdjKValues,
            smooth: false,
            lineStyle: {
              color: "#ff69b4",
              width: 1,
            },
            symbol: "none",
          },
          {
            name: "KDJ-D",
            type: "line",
            xAxisIndex: 2,
            yAxisIndex: 2,
            data: kdjDValues,
            smooth: false,
            lineStyle: {
              color: "#4169e1",
              width: 1,
            },
            symbol: "none",
          },
          {
            name: "KDJ-J",
            type: "line",
            xAxisIndex: 2,
            yAxisIndex: 2,
            data: kdjJValues,
            smooth: false,
            lineStyle: {
              color: "#ffff00",
              width: 1,
            },
            symbol: "none",
          },
          // MACD指标
          {
            name: "MACD",
            type: "line",
            xAxisIndex: 3,
            yAxisIndex: 3,
            data: macdValues,
            smooth: false,
            lineStyle: {
              color: "#4169e1",
              width: 1,
            },
            symbol: "none",
          },
          {
            name: "MACD-Signal",
            type: "line",
            xAxisIndex: 3,
            yAxisIndex: 3,
            data: macdSignalValues,
            smooth: false,
            lineStyle: {
              color: "#ff69b4",
              width: 1,
            },
            symbol: "none",
          },
          {
            name: "MACD-Hist",
            type: "bar",
            xAxisIndex: 3,
            yAxisIndex: 3,
            data: macdHistValues.map((val) => ({
              value: val,
              itemStyle: {
                color: val >= 0 ? "#22c55e" : "#ef4444",
              },
            })),
          },
        ],
      });
    };

    renderChart();

    return () => {
      mounted = false;
    };
  }, [sortedDaily, displayAdj, adjMap, indicators]);

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
