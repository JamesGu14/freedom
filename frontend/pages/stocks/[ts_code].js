import { startTransition, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/router";
import Link from "next/link";
import { apiFetch } from "../../lib/api";

const formatDate = (value) => {
  if (value == null || value === "") return "";
  const s = String(value).trim();
  if (s.length !== 8) return s || "";
  return `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}`;
};

/** 统一 trade_date 为字符串，便于与 indicators 的 trade_date 一致作为 Map key */
const normalizeTradeDate = (value) => {
  if (value == null || value === "") return "";
  const s = String(value).trim();
  return s.length === 8 ? s : String(value);
};

const normalizeDailyRows = (rows) => {
  const map = new Map();
  (rows || []).forEach((row) => {
    const key = normalizeTradeDate(row?.trade_date);
    if (!key) return;
    map.set(key, row);
  });
  return Array.from(map.values());
};

const normalizeAdjRows = (rows) => {
  const map = new Map();
  (rows || []).forEach((row) => {
    const key = normalizeTradeDate(row?.trade_date);
    if (!key) return;
    map.set(key, row);
  });
  return Array.from(map.values());
};

const OSCILLATOR_OPTIONS = [
  { key: "rsi", label: "RSI" },
  { key: "kdj", label: "KDJ" },
  { key: "wr", label: "WR" },
  { key: "cci", label: "CCI" },
  { key: "atr", label: "ATR" },
];

const OSCILLATOR_LABEL_MAP = {
  rsi: "RSI",
  kdj: "KDJ",
  wr: "WR",
  cci: "CCI",
  atr: "ATR",
};

const DETAIL_HISTORY_LIMIT = 480;
const STOCK_DETAIL_CACHE_TTL_MS = 5 * 60 * 1000;
const stockDetailCache = new Map();

const getStockDetailCache = (tsCode) => {
  const key = String(tsCode || "").trim().toUpperCase();
  const entry = stockDetailCache.get(key);
  if (!entry) return null;
  if (Date.now() - Number(entry.updatedAt || 0) > STOCK_DETAIL_CACHE_TTL_MS) {
    stockDetailCache.delete(key);
    return null;
  }
  return entry;
};

const setStockDetailCache = (tsCode, patch) => {
  const key = String(tsCode || "").trim().toUpperCase();
  if (!key) return;
  const previous = stockDetailCache.get(key) || {};
  stockDetailCache.set(key, {
    ...previous,
    ...patch,
    updatedAt: Date.now(),
  });
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
  const [sectorMembers, setSectorMembers] = useState([]);
  const [indicatorsLoading, setIndicatorsLoading] = useState(false);
  const [sectorLoading, setSectorLoading] = useState(false);
  const [adjPage, setAdjPage] = useState(1);
  const [adjPageSize] = useState(10);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [chartError, setChartError] = useState("");
  const [backHref, setBackHref] = useState("/");
  const [chartReady, setChartReady] = useState(false);
  const [oscillatorMode, setOscillatorMode] = useState("rsi");

  const setChartEl = useCallback((el) => {
    chartRef.current = el;
    setChartReady(!!el);
  }, []);


  useEffect(() => {
    // 从 URL 参数中读取返回链接
    const { returnUrl } = router.query;
    if (returnUrl && typeof returnUrl === "string") {
      setBackHref(decodeURIComponent(returnUrl));
    }
    // no-op
  }, [router.query]);

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

  const applyCacheEntry = useCallback((entry) => {
    if (!entry) return;
    if (Array.isArray(entry.daily)) {
      setDaily(entry.daily);
    }
    if (Array.isArray(entry.adjFactor)) {
      setAdjFactor(entry.adjFactor);
    }
    if (entry.stockInfo) {
      setStockInfo(entry.stockInfo);
    }
    if (Array.isArray(entry.indicators)) {
      setIndicators(entry.indicators);
    }
    if (Array.isArray(entry.sectorMembers)) {
      setSectorMembers(entry.sectorMembers);
    }
  }, []);

  useEffect(() => {
    if (!tsCode || typeof tsCode !== "string") {
      return;
    }

    let cancelled = false;
    const normalizedCode = String(tsCode).trim().toUpperCase();
    const cached = getStockDetailCache(normalizedCode);
    const hasPrimaryCache = Boolean(
      cached &&
      Array.isArray(cached.daily) &&
      cached.daily.length > 0 &&
      Array.isArray(cached.adjFactor)
    );
    const hasSecondaryCache = Boolean(
      cached &&
      Array.isArray(cached.indicators) &&
      Array.isArray(cached.sectorMembers)
    );

    setError("");
    if (hasPrimaryCache || hasSecondaryCache) {
      applyCacheEntry(cached);
    } else {
      setDaily([]);
      setAdjFactor([]);
      setIndicators([]);
      setStockInfo(null);
      setSectorMembers([]);
    }
    setLoading(!hasPrimaryCache);
    setIndicatorsLoading(!hasSecondaryCache);
    setSectorLoading(!hasSecondaryCache);

    const loadPrimary = async () => {
      if (hasPrimaryCache) {
        return;
      }
      try {
        const [candlesRes, basicRes] = await Promise.all([
          apiFetch(`/stocks/${normalizedCode}/candles?limit=${DETAIL_HISTORY_LIMIT}`),
          apiFetch(`/stocks/${normalizedCode}/basic`),
        ]);
        if (!candlesRes.ok) {
          throw new Error(`加载失败: ${candlesRes.status}`);
        }
        const data = await candlesRes.json();
        const nextDaily = normalizeDailyRows(data.daily || []);
        const nextAdjFactor = normalizeAdjRows(data.adj_factor || []);
        let nextStockInfo = null;
        if (basicRes.ok) {
          nextStockInfo = await basicRes.json();
        }
        if (cancelled) {
          return;
        }
        setDaily(nextDaily);
        setAdjFactor(nextAdjFactor);
        setStockInfo(nextStockInfo);
        setStockDetailCache(normalizedCode, {
          daily: nextDaily,
          adjFactor: nextAdjFactor,
          stockInfo: nextStockInfo,
        });
      } catch (err) {
        if (!cancelled && !hasPrimaryCache) {
          setError(err.message || "加载失败");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    const loadSecondary = async () => {
      if (hasSecondaryCache) {
        return;
      }
      try {
        const [featuresRes, sectorRes] = await Promise.all([
          apiFetch(`/stocks/${normalizedCode}/features?limit=${DETAIL_HISTORY_LIMIT}`),
          apiFetch(`/sectors/members?ts_code=${encodeURIComponent(normalizedCode)}&is_new=Y&page_size=1`),
        ]);
        let nextIndicators = [];
        let nextSectorMembers = [];
        if (featuresRes.ok) {
          const featuresData = await featuresRes.json();
          nextIndicators = featuresData.indicators || [];
        }
        if (sectorRes.ok) {
          const sectorData = await sectorRes.json();
          nextSectorMembers = sectorData.items || [];
        }
        if (cancelled) {
          return;
        }
        startTransition(() => {
          setIndicators(nextIndicators);
          setSectorMembers(nextSectorMembers);
        });
        setStockDetailCache(normalizedCode, {
          indicators: nextIndicators,
          sectorMembers: nextSectorMembers,
        });
      } finally {
        if (!cancelled) {
          setIndicatorsLoading(false);
          setSectorLoading(false);
        }
      }
    };

    loadPrimary();

    let idleId = null;
    let timerId = null;
    const scheduleSecondary = () => {
      if (typeof window !== "undefined" && typeof window.requestIdleCallback === "function") {
        idleId = window.requestIdleCallback(() => {
          void loadSecondary();
        }, { timeout: 1000 });
      } else {
        timerId = window.setTimeout(() => {
          void loadSecondary();
        }, hasPrimaryCache ? 0 : 200);
      }
    };
    scheduleSecondary();

    return () => {
      cancelled = true;
      if (idleId !== null && typeof window !== "undefined" && typeof window.cancelIdleCallback === "function") {
        window.cancelIdleCallback(idleId);
      }
      if (timerId !== null && typeof window !== "undefined") {
        window.clearTimeout(timerId);
      }
    };
  }, [applyCacheEntry, tsCode]);

  useEffect(() => {
    setAdjPage(1);
  }, [displayAdj.length]);

  useEffect(() => {
    let mounted = true;

    const renderChart = async () => {
      if (!chartRef.current || sortedDaily.length === 0) {
        return;
      }
      if (!chartInstanceRef.current) {
        const echartsModule = await import("echarts");
        const echarts = echartsModule?.default ?? echartsModule;
        if (!echarts?.init) {
          throw new Error("ECharts 初始化失败");
        }
        if (!mounted || !chartRef.current) return;
        chartInstanceRef.current = echarts.init(chartRef.current, null, { renderer: "canvas" });
      }
      // 等待容器完成布局后再 setOption，避免宽高为 0 导致不绘制
      await new Promise((r) => requestAnimationFrame(r));
      if (!mounted || !chartInstanceRef.current) return;
      const toNum = (v) => {
        if (v == null || v === "") return null;
        const n = Number(v);
        return Number.isFinite(n) ? n : null;
      };
      // 兼容接口字段：优先 open/close/low/high/vol，备选 open_price 等
      const ohlc = (item) => ({
        open: toNum(item.open ?? item.open_price),
        close: toNum(item.close ?? item.close_price),
        low: toNum(item.low ?? item.low_price),
        high: toNum(item.high ?? item.high_price),
        vol: toNum(item.vol ?? item.volumn ?? item.volume),
      });
      const dates = sortedDaily.map((item) => formatDate(item.trade_date));
      const candles = sortedDaily.map((item) => {
        const { open: o, close: c, low: l, high: h } = ohlc(item);
        return [o ?? 0, c ?? 0, l ?? 0, h ?? 0];
      });

      // Create indicator map for quick lookup（key 统一为字符串，避免 number/string 不一致）
      const indicatorMap = new Map();
      (indicators || []).forEach((ind) => {
        const key = normalizeTradeDate(ind.trade_date);
        if (key) indicatorMap.set(key, ind);
      });

      const getInd = (item) => indicatorMap.get(normalizeTradeDate(item.trade_date));

      // Get MA values aligned with daily data
      const ma5Values = sortedDaily.map((item) => getInd(item)?.ma5 ?? null);
      const ma10Values = sortedDaily.map((item) => getInd(item)?.ma10 ?? null);
      const ma20Values = sortedDaily.map((item) => getInd(item)?.ma20 ?? null);
      const ma30Values = sortedDaily.map((item) => getInd(item)?.ma30 ?? null);
      const ma60Values = sortedDaily.map((item) => getInd(item)?.ma60 ?? null);
      const ma90Values = sortedDaily.map((item) => getInd(item)?.ma90 ?? null);
      const ma250Values = sortedDaily.map((item) => getInd(item)?.ma250 ?? null);
      const bollUpperValues = sortedDaily.map((item) => getInd(item)?.boll_upper ?? null);
      const bollMiddleValues = sortedDaily.map((item) => getInd(item)?.boll_middle ?? null);
      const bollLowerValues = sortedDaily.map((item) => getInd(item)?.boll_lower ?? null);
      // Get RSI values
      const rsi6Values = sortedDaily.map((item) => getInd(item)?.rsi6 ?? null);
      const rsi12Values = sortedDaily.map((item) => getInd(item)?.rsi12 ?? null);
      const rsi24Values = sortedDaily.map((item) => getInd(item)?.rsi24 ?? null);
      const wr14Values = sortedDaily.map((item) => getInd(item)?.wr ?? null);
      const wr28Values = sortedDaily.map((item) => getInd(item)?.wr1 ?? null);
      const cciValues = sortedDaily.map((item) => getInd(item)?.cci ?? null);
      const atrValues = sortedDaily.map((item) => getInd(item)?.atr ?? null);
      // Get KDJ values
      const kdjKValues = sortedDaily.map((item) => getInd(item)?.kdj_k ?? null);
      const kdjDValues = sortedDaily.map((item) => getInd(item)?.kdj_d ?? null);
      const kdjJValues = sortedDaily.map((item) => getInd(item)?.kdj_j ?? null);
      // Get MACD values
      const macdValues = sortedDaily.map((item) => getInd(item)?.macd ?? null);
      const macdSignalValues = sortedDaily.map((item) => getInd(item)?.macd_signal ?? null);
      const macdHistValues = sortedDaily.map((item) => getInd(item)?.macd_hist ?? null);
      const volumeBars = sortedDaily.map((item) => {
        const { open: o, close: c, vol: v } = ohlc(item);
        return {
          value: v ?? 0,
          itemStyle: {
            color: (c ?? 0) >= (o ?? 0) ? "#ef4444" : "#22c55e",
          },
        };
      });
      const totalCount = sortedDaily.length;
      const startIndex = Math.max(totalCount - 120, 0);
      const startPercent = totalCount > 1 ? (startIndex / (totalCount - 1)) * 100 : 0;
      const oscillatorLabel = OSCILLATOR_LABEL_MAP[oscillatorMode] || "RSI";

      let oscillatorAxis = {
        gridIndex: 2,
        scale: true,
        axisLabel: { color: "#999999" },
        splitLine: { lineStyle: { color: "#333333" } },
      };
      if (oscillatorMode === "rsi") {
        oscillatorAxis = {
          gridIndex: 2,
          min: 0,
          max: 100,
          axisLabel: { color: "#999999" },
          splitLine: { lineStyle: { color: "#333333" } },
        };
      } else if (oscillatorMode === "wr") {
        oscillatorAxis = {
          gridIndex: 2,
          min: -100,
          max: 0,
          axisLabel: { color: "#999999" },
          splitLine: { lineStyle: { color: "#333333" } },
        };
      }

      let oscillatorSeries = [];
      if (oscillatorMode === "rsi") {
        oscillatorSeries = [
          {
            name: "RSI6",
            type: "line",
            xAxisIndex: 2,
            yAxisIndex: 2,
            data: rsi6Values,
            smooth: false,
            lineStyle: { color: "#eab308", width: 1 },
            symbol: "none",
          },
          {
            name: "RSI12",
            type: "line",
            xAxisIndex: 2,
            yAxisIndex: 2,
            data: rsi12Values,
            smooth: false,
            lineStyle: { color: "#60a5fa", width: 1 },
            symbol: "none",
          },
          {
            name: "RSI24",
            type: "line",
            xAxisIndex: 2,
            yAxisIndex: 2,
            data: rsi24Values,
            smooth: false,
            lineStyle: { color: "#f43f5e", width: 1 },
            symbol: "none",
          },
        ];
      } else if (oscillatorMode === "kdj") {
        oscillatorSeries = [
          {
            name: "KDJ-K",
            type: "line",
            xAxisIndex: 2,
            yAxisIndex: 2,
            data: kdjKValues,
            smooth: false,
            lineStyle: { color: "#ff69b4", width: 1 },
            symbol: "none",
          },
          {
            name: "KDJ-D",
            type: "line",
            xAxisIndex: 2,
            yAxisIndex: 2,
            data: kdjDValues,
            smooth: false,
            lineStyle: { color: "#4169e1", width: 1 },
            symbol: "none",
          },
          {
            name: "KDJ-J",
            type: "line",
            xAxisIndex: 2,
            yAxisIndex: 2,
            data: kdjJValues,
            smooth: false,
            lineStyle: { color: "#ffff00", width: 1 },
            symbol: "none",
          },
        ];
      } else if (oscillatorMode === "wr") {
        oscillatorSeries = [
          {
            name: "WR14",
            type: "line",
            xAxisIndex: 2,
            yAxisIndex: 2,
            data: wr14Values,
            smooth: false,
            lineStyle: { color: "#34d399", width: 1 },
            symbol: "none",
          },
          {
            name: "WR28",
            type: "line",
            xAxisIndex: 2,
            yAxisIndex: 2,
            data: wr28Values,
            smooth: false,
            lineStyle: { color: "#f472b6", width: 1 },
            symbol: "none",
          },
        ];
      } else if (oscillatorMode === "cci") {
        oscillatorSeries = [
          {
            name: "CCI",
            type: "line",
            xAxisIndex: 2,
            yAxisIndex: 2,
            data: cciValues,
            smooth: false,
            lineStyle: { color: "#f59e0b", width: 1 },
            symbol: "none",
          },
        ];
      } else if (oscillatorMode === "atr") {
        oscillatorSeries = [
          {
            name: "ATR",
            type: "line",
            xAxisIndex: 2,
            yAxisIndex: 2,
            data: atrValues,
            smooth: false,
            lineStyle: { color: "#22d3ee", width: 1 },
            symbol: "none",
          },
        ];
      }

      chartInstanceRef.current.setOption(
        {
          backgroundColor: "#000000",
          animation: false,
          grid: [
            { left: 40, right: 20, top: 30, height: 300 },
            { left: 40, right: 20, top: 350, height: 90 },
            { left: 40, right: 20, top: 470, height: 170 },
            { left: 40, right: 20, top: 670, height: 190 },
          ],
          legend: {
            top: 4,
            left: 44,
            textStyle: { color: "#999999", fontSize: 11 },
            itemWidth: 10,
            itemHeight: 6,
            selected: {
              MA90: false,
              MA250: false,
              "BOLL-UP": false,
              "BOLL-DN": false,
            },
          },
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
              const formatPct = (val) => {
                if (val == null || val === "" || Number.isNaN(val)) return "-";
                const prefix = val > 0 ? "+" : "";
                return `${prefix}${val.toFixed(2)}%`;
              };
              const index = params[0].dataIndex;
              const date = dates[index];
              const lines = [`${date}`];

              // K线数据 - 从原始数据读取，确保准确性（兼容不同字段名）
              if (index >= 0 && index < sortedDaily.length) {
                const item = sortedDaily[index];
                const o = item.open ?? item.open_price;
                const c = item.close ?? item.close_price;
                const l = item.low ?? item.low_price;
                const h = item.high ?? item.high_price;
                const prevClose =
                  item.pre_close ??
                  item.preclose ??
                  item.prev_close ??
                  (index > 0
                    ? sortedDaily[index - 1]?.close ?? sortedDaily[index - 1]?.close_price
                    : null);
                const pct =
                  prevClose && Number(prevClose) > 0 && c != null
                    ? ((Number(c) - Number(prevClose)) / Number(prevClose)) * 100
                    : null;
                lines.push(`涨跌幅: ${formatPct(pct)}`);
                lines.push(
                  `开盘: ${formatNumber(o)}`,
                  `收盘: ${formatNumber(c)}`,
                  `最低: ${formatNumber(l)}`,
                  `最高: ${formatNumber(h)}`
                );
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
              scale: true,
              axisLabel: { color: "#999999" },
              splitLine: { show: false },
            },
            oscillatorAxis,
            {
              gridIndex: 3,
              scale: true,
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
              top: 472,
              style: {
                text: oscillatorLabel,
                fontSize: 14,
                fontWeight: "bold",
                fill: "#ffffff",
              },
            },
            {
              type: "text",
              left: 50,
              top: 672,
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
              name: "MA60",
              type: "line",
              data: ma60Values,
              smooth: false,
              lineStyle: {
                color: "#f97316",
                width: 1,
              },
              symbol: "none",
            },
            {
              name: "MA90",
              type: "line",
              data: ma90Values,
              smooth: false,
              lineStyle: {
                color: "#22d3ee",
                width: 1,
              },
              symbol: "none",
            },
            {
              name: "MA250",
              type: "line",
              data: ma250Values,
              smooth: false,
              lineStyle: {
                color: "#9ca3af",
                width: 1,
              },
              symbol: "none",
            },
            {
              name: "BOLL-UP",
              type: "line",
              data: bollUpperValues,
              smooth: false,
              lineStyle: {
                color: "#14b8a6",
                width: 1,
                type: "dashed",
              },
              symbol: "none",
            },
            {
              name: "BOLL-MID",
              type: "line",
              data: bollMiddleValues,
              smooth: false,
              lineStyle: {
                color: "#a3e635",
                width: 1,
                type: "dashed",
              },
              symbol: "none",
            },
            {
              name: "BOLL-DN",
              type: "line",
              data: bollLowerValues,
              smooth: false,
              lineStyle: {
                color: "#fb7185",
                width: 1,
                type: "dashed",
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
            ...oscillatorSeries,
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
              data: macdHistValues.map((val) =>
                val == null
                  ? null
                  : {
                      value: val,
                      itemStyle: {
                        color: val >= 0 ? "#22c55e" : "#ef4444",
                      },
                    }
              ),
            },
          ],
        },
        { notMerge: true }
      );
      requestAnimationFrame(() => {
        if (chartInstanceRef.current) chartInstanceRef.current.resize();
      });
      if (chartRef.current && chartError) {
        setChartError("");
      }
    };

    renderChart().catch((err) => {
      setChartError(err?.message || "图表渲染失败");
    });

    return () => {
      mounted = false;
    };
  }, [sortedDaily, indicators, chartReady, oscillatorMode]);

  useEffect(() => {
    if (!chartInstanceRef.current || sortedDaily.length === 0) return;
    const id = requestAnimationFrame(() => {
      chartInstanceRef.current?.resize();
    });
    return () => cancelAnimationFrame(id);
  }, [sortedDaily.length]);

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

  const sectorBadges = useMemo(() => {
    if (sectorLoading || sectorMembers.length === 0) return null;
    const item = sectorMembers[0];
    const version = item?.version || "2021";
    const parts = [];
    if (item?.l1_name) {
      parts.push(
        <Link
          key="l1"
          className="sector-badge"
          href={`/sectors/${item.l1_code}?version=${version}`}
        >
          {item.l1_name}
        </Link>
      );
    }
    if (item?.l2_name && item?.l2_code) {
      parts.push(
        <Link
          key="l2"
          className="sector-badge"
          href={`/sectors/${item.l2_code}?version=${version}`}
        >
          {item.l2_name}
        </Link>
      );
    }
    if (item?.l3_name && item?.l3_code) {
      parts.push(
        <Link
          key="l3"
          className="sector-badge"
          href={`/sectors/${item.l3_code}?version=${version}`}
        >
          {item.l3_name}
        </Link>
      );
    }
    return parts.length > 0 ? parts : null;
  }, [sectorMembers, sectorLoading]);

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
          {sectorBadges && (
            <div className="header-badges">
              <span className="header-badges-label">申万行业：</span>
              {sectorBadges}
              <Link className="link-button header-badges-more" href="/sectors">
                板块
              </Link>
            </div>
          )}
        </div>
        <Link className="primary" href={backHref}>
          返回
        </Link>
      </header>

      {error ? <div className="error">{error}</div> : null}
      {chartError ? <div className="error">{chartError}</div> : null}

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
            <div className="indicator-switcher">
              <span className="indicator-switcher-label">副图指标</span>
              {indicatorsLoading ? <span className="indicator-switcher-label">技术指标加载中...</span> : null}
              {OSCILLATOR_OPTIONS.map((option) => (
                <button
                  key={option.key}
                  type="button"
                  className={`indicator-switcher-btn ${oscillatorMode === option.key ? "active" : ""}`}
                  onClick={() => setOscillatorMode(option.key)}
                >
                  {option.label}
                </button>
              ))}
            </div>
            <div className="chart-canvas" ref={setChartEl} />
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
