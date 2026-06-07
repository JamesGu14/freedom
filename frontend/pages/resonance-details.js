import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/router";
import Link from "next/link";
import { apiFetch } from "../lib/api";

const formatDate = (value) => {
  if (!value) return "";
  const s = String(value).trim();
  if (s.length !== 8) return s;
  return `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}`;
};

const RESONANCE_LABELS = {
  very_strong: "极强共振 (14+)",
  strong: "强共振 (9+)",
  normal: "普通共振 (5+)",
};

function calculateMA(data, period) {
  const result = [];
  for (let i = 0; i < data.length; i++) {
    if (i < period - 1) {
      result.push(null);
      continue;
    }
    let sum = 0;
    for (let j = 0; j < period; j++) {
      sum += data[i - j];
    }
    result.push(sum / period);
  }
  return result;
}

function CandlestickChart({ candles }) {
  const chartRef = useRef(null);
  const chartInstanceRef = useRef(null);

  useEffect(() => {
    if (!chartRef.current || !candles.length) return;

    let mounted = true;

    const render = async () => {
      if (chartInstanceRef.current) {
        chartInstanceRef.current.dispose();
        chartInstanceRef.current = null;
      }

      const echartsModule = await import("echarts");
      const echarts = echartsModule?.default ?? echartsModule;
      if (!echarts?.init || !mounted || !chartRef.current) return;

      const chart = echarts.init(chartRef.current, null, { renderer: "canvas" });
      chartInstanceRef.current = chart;

      await new Promise((r) => requestAnimationFrame(r));
      if (!mounted || !chartInstanceRef.current) return;

      const dates = candles.map((c) => c.trade_date);
      const toNum = (v) => {
        if (v == null || v === "") return null;
        const n = Number(v);
        return Number.isFinite(n) ? n : null;
      };
      const candleData = candles.map((c) => [toNum(c.open), toNum(c.close), toNum(c.low), toNum(c.high)]);
      const closes = candles.map((c) => toNum(c.close));
      const ma5 = calculateMA(closes, 5);
      const ma10 = calculateMA(closes, 10);
      const ma20 = calculateMA(closes, 20);

      const option = {
        grid: { left: 50, right: 20, top: 20, bottom: 30 },
        xAxis: { type: "category", data: dates, axisLabel: { fontSize: 10 } },
        yAxis: { type: "value", scale: true, axisLabel: { fontSize: 10 } },
        series: [
          {
            type: "candlestick",
            data: candleData,
            itemStyle: {
              color: "#ea3943",
              color0: "#00a650",
              borderColor: "#ea3943",
              borderColor0: "#00a650",
            },
          },
          { name: "MA5", type: "line", data: ma5, smooth: true, lineStyle: { width: 1 }, symbol: "none" },
          { name: "MA10", type: "line", data: ma10, smooth: true, lineStyle: { width: 1 }, symbol: "none" },
          { name: "MA20", type: "line", data: ma20, smooth: true, lineStyle: { width: 1 }, symbol: "none" },
        ],
        tooltip: { trigger: "axis" },
        legend: { data: ["MA5", "MA10", "MA20"], top: 0, textStyle: { fontSize: 10 } },
      };

      chart.setOption(option);
    };

    render();

    return () => {
      mounted = false;
      if (chartInstanceRef.current) {
        chartInstanceRef.current.dispose();
        chartInstanceRef.current = null;
      }
    };
  }, [candles]);

  return <div ref={chartRef} className="stock-detail-chart" style={{ height: 300 }} />;
}

function StockDetailCard({ stock, onUpdateState }) {
  const [candles, setCandles] = useState([]);
  const [chartLoading, setChartLoading] = useState(true);
  const [chartError, setChartError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setChartLoading(true);
    setChartError("");

    apiFetch(`/stocks/${stock.ts_code}/candles?limit=60`)
      .then(async (res) => {
        if (!res.ok) throw new Error(`加载失败: ${res.status}`);
        const data = await res.json();
        if (!cancelled) setCandles(data.daily || []);
      })
      .catch((err) => {
        if (!cancelled) setChartError(err.message);
      })
      .finally(() => {
        if (!cancelled) setChartLoading(false);
      });

    return () => { cancelled = true; };
  }, [stock.ts_code]);

  const isAcknowledged = stock.user_state === "acknowledged";
  const isIgnored = stock.user_state === "ignored";

  return (
    <div className={`stock-detail-card ${isAcknowledged ? "acknowledged" : ""}`}>
      <div className="stock-detail-header">
        <h3>{stock.name || stock.ts_code} ({stock.ts_code})</h3>
        <span>{stock.industry || "-"}</span>
        <span>收盘 {stock.close || "-"}</span>
        <span className={Number(stock.pct_chg) > 0 ? "text-red" : Number(stock.pct_chg) < 0 ? "text-green" : ""}>
          {stock.pct_chg ? `${Number(stock.pct_chg).toFixed(2)}%` : "-"}
        </span>
      </div>

      {chartLoading && <div className="chart-loading">加载 K 线数据中...</div>}
      {chartError && <div className="chart-error">{chartError}</div>}

      {!chartLoading && !chartError && candles.length > 0 && (
        <CandlestickChart candles={candles} />
      )}

      <div className="stock-detail-actions">
        {isIgnored ? (
          <>
            <button type="button" onClick={() => onUpdateState(stock.ts_code, null)}>取消忽略</button>
            <button type="button" onClick={() => onUpdateState(stock.ts_code, "acknowledged")}>认可</button>
          </>
        ) : isAcknowledged ? (
          <>
            <button type="button" onClick={() => onUpdateState(stock.ts_code, null)}>取消认可</button>
            <button type="button" onClick={() => onUpdateState(stock.ts_code, "ignored")}>忽略</button>
          </>
        ) : (
          <>
            <button type="button" onClick={() => onUpdateState(stock.ts_code, "ignored")}>忽略</button>
            <button type="button" onClick={() => onUpdateState(stock.ts_code, "acknowledged")}>认可</button>
          </>
        )}
      </div>
    </div>
  );
}

export default function ResonanceDetailsPage() {
  const router = useRouter();
  const { trade_date, signal_side, resonance_level } = router.query;

  const [stocks, setStocks] = useState([]);
  const [filter, setFilter] = useState("all");
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const pageSize = 5;

  useEffect(() => {
    if (!trade_date || !signal_side || !resonance_level) return;

    let cancelled = false;
    setLoading(true);
    setError("");

    apiFetch(`/daily-stock-signals/overview?trade_date=${trade_date}`)
      .then(async (res) => {
        if (!res.ok) throw new Error("加载失败");
        const data = await res.json();
        if (cancelled) return;

        const resonanceGroups = signal_side === "buy" ? data.buy_resonance : data.sell_resonance;
        const group = resonanceGroups.find((g) => g.resonance_level === resonance_level);

        if (group) {
          setStocks(group.stocks || []);
        } else {
          setStocks([]);
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err.message || "加载失败");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => { cancelled = true; };
  }, [trade_date, signal_side, resonance_level]);

  useEffect(() => { setPage(1); }, [filter]);

  const filteredStocks = useMemo(() => {
    switch (filter) {
      case "acknowledged":
        return stocks.filter((s) => s.user_state === "acknowledged");
      case "active":
        return stocks.filter((s) => s.user_state !== "ignored");
      case "all":
      default:
        return stocks;
    }
  }, [stocks, filter]);

  const totalPages = Math.max(Math.ceil(filteredStocks.length / pageSize), 1);
  const pageItems = filteredStocks.slice((page - 1) * pageSize, page * pageSize);

  const updateStockState = useCallback(async (tsCode, newState) => {
    const previousState = stocks.find((s) => s.ts_code === tsCode)?.user_state;

    setStocks((prev) => prev.map((s) =>
      s.ts_code === tsCode ? { ...s, user_state: newState } : s
    ));

    try {
      const res = await apiFetch("/daily-stock-signals/resonance/state", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          trade_date,
          ts_code: tsCode,
          signal_side,
          resonance_level,
          user_state: newState,
        }),
      });

      if (!res.ok) {
        throw new Error(`更新失败: ${res.status}`);
      }
    } catch (err) {
      setStocks((prev) => prev.map((s) =>
        s.ts_code === tsCode ? { ...s, user_state: previousState } : s
      ));
      alert(err.message || "更新失败，请重试");
    }
  }, [stocks, trade_date, signal_side, resonance_level]);

  if (!trade_date || !signal_side || !resonance_level) {
    return (
      <main className="page">
        <div className="error">参数错误：缺少必要的 URL 参数</div>
        <Link href="/" className="link-button">返回首页</Link>
      </main>
    );
  }

  return (
    <main className="page">
      <header className="header">
        <div>
          <p className="eyebrow">Quant Platform</p>
          <h1>极强共振详情</h1>
          <p className="subtitle">
            {formatDate(trade_date)} · {signal_side === "buy" ? "买入" : "卖出"} · {RESONANCE_LABELS[resonance_level] || resonance_level}
          </p>
        </div>
        <Link href="/" className="link-button">返回首页</Link>
      </header>

      {error && <div className="error">{error}</div>}

      {loading ? (
        <div className="loading-container">
          <div className="spinner"></div>
          <p>加载中...</p>
        </div>
      ) : (
        <>
          <div className="filter-tabs">
            <button type="button" className={filter === "all" ? "filter-tab active" : "filter-tab"} onClick={() => setFilter("all")}>
              全部 ({stocks.length})
            </button>
            <button type="button" className={filter === "acknowledged" ? "filter-tab active" : "filter-tab"} onClick={() => setFilter("acknowledged")}>
              只看认可 ({stocks.filter((s) => s.user_state === "acknowledged").length})
            </button>
            <button type="button" className={filter === "active" ? "filter-tab active" : "filter-tab"} onClick={() => setFilter("active")}>
              认可+未标记 ({stocks.filter((s) => s.user_state !== "ignored").length})
            </button>
          </div>

          <div className="resonance-detail-list">
            {pageItems.length === 0 ? (
              <div className="empty-state">
                <p>暂无符合条件的股票</p>
              </div>
            ) : (
              pageItems.map((stock) => (
                <StockDetailCard
                  key={stock.ts_code}
                  stock={stock}
                  onUpdateState={updateStockState}
                />
              ))
            )}
          </div>

          {totalPages > 1 && (
            <div className="pagination">
              <button
                type="button"
                className="pagination__btn"
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
              >
                ‹ 上一页
              </button>
              <span className="pagination__info">
                {page} / {totalPages} 页（共 {filteredStocks.length} 只）
              </span>
              <button
                type="button"
                className="pagination__btn"
                disabled={page >= totalPages}
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              >
                下一页 ›
              </button>
            </div>
          )}
        </>
      )}
    </main>
  );
}
