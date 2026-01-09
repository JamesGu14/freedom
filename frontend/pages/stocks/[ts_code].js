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
      const [candlesRes, basicRes] = await Promise.all([
        fetch(`${API_BASE}/stocks/${tsCode}/candles`),
        fetch(`${API_BASE}/stocks/${tsCode}/basic`),
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
        backgroundColor: "transparent",
        grid: [
          { left: 40, right: 20, top: 20, height: "60%" },
          { left: 40, right: 20, top: "70%", height: "20%" },
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
        axisPointer: { link: [{ xAxisIndex: [0, 1] }] },
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
        ],
        dataZoom: [
          {
            type: "inside",
            xAxisIndex: [0, 1],
            start: startPercent,
            end: 100,
          },
          {
            type: "slider",
            xAxisIndex: [0, 1],
            start: startPercent,
            end: 100,
            top: "92%",
            height: 18,
          },
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
          {
            name: "成交量",
            type: "bar",
            xAxisIndex: 1,
            yAxisIndex: 1,
            data: volumeBars,
          },
        ],
      });
    };

    renderChart();

    return () => {
      mounted = false;
    };
  }, [sortedDaily, displayAdj, adjMap]);

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
