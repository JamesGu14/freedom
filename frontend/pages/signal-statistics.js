import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { apiFetch } from "../lib/api";

function PatternDetailPopup({ stock, tradeDate, onClose }) {
  const [details, setDetails] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await apiFetch(`/daily-stock-signals/stock/${encodeURIComponent(stock.ts_code)}/patterns?trade_date=${tradeDate}`);
        const data = res.ok ? await res.json() : null;
        if (!cancelled) setDetails(data);
      } catch {
        if (!cancelled) setDetails(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [stock.ts_code, tradeDate]);

  const patterns = details?.patterns || [];
  const weightedScore = details?.weighted_score || stock.weighted_score || 0;
  const resonanceLevel = details?.resonance_level || stock.resonance_level || "";

  const groupedPatterns = patterns.reduce((groups, p) => {
    const cat = p.category || "其他";
    if (!groups[cat]) groups[cat] = [];
    groups[cat].push(p);
    return groups;
  }, {});

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box modal-box--pattern" onClick={(e) => e.stopPropagation()}>
        <div className="modal-box__header">
          <h3>{stock.name || stock.ts_code} · {formatDate(tradeDate)}</h3>
          <button type="button" className="modal-box__close" onClick={onClose}>✕</button>
        </div>
        <div className="modal-box__body">
          {loading ? (
            <div style={{ padding: 24, textAlign: "center", color: "var(--muted)" }}>加载中...</div>
          ) : (
            <div>
              <div className="pattern-summary">
                <div className="pattern-score">
                  <span className="pattern-score__value">{weightedScore}</span>
                  <span className="pattern-score__label">综合得分</span>
                </div>
                <div className="pattern-level">
                  <span className={`pattern-level__badge pattern-level__badge--${resonanceLevel}`}>
                    {RESONANCE_LABELS[resonanceLevel] || resonanceLevel}
                  </span>
                </div>
              </div>
              <div className="pattern-categories">
                {Object.entries(groupedPatterns).map(([category, items]) => (
                  <div key={category} className="pattern-category">
                    <h4 className="pattern-category__title">{category}</h4>
                    <div className="pattern-category__items">
                      {items.map((p) => (
                        <span key={p.pattern} className="pattern-tag">
                          {p.pattern}
                          <span className="pattern-tag__weight">+{p.weight}</span>
                        </span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
              <div className="pattern-stock-info">
                <span>收盘 {formatNumber(stock.close)}</span>
                <span className={Number(stock.pct_chg) > 0 ? "text-red" : Number(stock.pct_chg) < 0 ? "text-green" : ""}>{formatPct(stock.pct_chg)}</span>
                <span>量比 {formatNumber(stock.volume_ratio)}</span>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

const normalizeDateValue = (value) => {
  if (!value) return "";
  const cleaned = String(value).replace(/-/g, "");
  return cleaned.length === 8 ? cleaned : "";
};

const formatDate = (value) => {
  const normalized = normalizeDateValue(value);
  if (!normalized) return value || "-";
  return `${normalized.slice(0, 4)}-${normalized.slice(4, 6)}-${normalized.slice(6, 8)}`;
};

const formatNumber = (value, digits = 2) => {
  if (value === null || value === undefined || value === "") return "-";
  const num = Number(value);
  if (Number.isNaN(num)) return String(value);
  return num.toLocaleString("zh-CN", { maximumFractionDigits: digits });
};

const formatPct = (value) => {
  if (value === null || value === undefined || value === "") return "-";
  const num = Number(value);
  if (Number.isNaN(num)) return String(value);
  const prefix = num > 0 ? "+" : "";
  return `${prefix}${num.toFixed(2)}%`;
};

const RESONANCE_LABELS = {
  very_strong: "极强共振",
  strong: "强共振",
  normal: "普通共振",
};

const getResonanceLabel = (l) => RESONANCE_LABELS[l] || l;

const PAGE_SIZE = 20;

const StockList = ({ stocks = [] }) => {
  const [page, setPage] = useState(1);
  const [patternStock, setPatternStock] = useState(null);

  useEffect(() => { setPage(1); }, [stocks]);

  if (!stocks.length) {
    return <div className="signal-empty">暂无符合条件的股票</div>;
  }

  const totalPages = Math.ceil(stocks.length / PAGE_SIZE);
  const pageItems = stocks.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  return (
    <div>
      <div className="signal-stock-grid">
        {pageItems.map((item) => (
          <div key={item.ts_code} className="signal-stock-cell">
            <div className="signal-stock-cell__head">
              <span className="signal-stock-cell__name">{item.name || item.ts_code}</span>
              <span className="signal-stock-cell__code">{item.ts_code}</span>
            </div>
            <div className="signal-stock-cell__info">
              <span>{item.industry || "-"}</span>
              <span>收盘 {formatNumber(item.close)}</span>
              <span className={Number(item.pct_chg) > 0 ? "text-red" : Number(item.pct_chg) < 0 ? "text-green" : ""}>
                {formatPct(item.pct_chg)}
              </span>
              <span>量比 {formatNumber(item.volume_ratio)}</span>
            </div>
            <div className="signal-stock-cell__tags">
              <span className="signal-tag">{item.resonance_count} 次共振</span>
              <span className="signal-tag">{getResonanceLabel(item.latest_resonance_level)}</span>
            </div>
            <div className="signal-stock-cell__foot">
              <span>最新: {formatDate(item.latest_trade_date)}</span>
              <div className="signal-stock-cell__actions">
                <button type="button" className="link-button" onClick={() => setPatternStock(item)}>详情</button>
                <Link className="link-button" href={`/stocks/${item.ts_code}`}>K线</Link>
              </div>
            </div>
          </div>
        ))}
      </div>
      {totalPages > 1 && (
        <div className="pagination">
          <button type="button" className="pagination__btn" disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>‹ 上一页</button>
          <span className="pagination__info">{page} / {totalPages} 页（共 {stocks.length} 只）</span>
          <button type="button" className="pagination__btn" disabled={page >= totalPages} onClick={() => setPage((p) => Math.min(totalPages, p + 1))}>下一页 ›</button>
        </div>
      )}
      {patternStock && (
        <PatternDetailPopup stock={patternStock} tradeDate={patternStock.latest_trade_date} onClose={() => setPatternStock(null)} />
      )}
    </div>
  );
};

const StatisticsPanel = ({ panel }) => (
  <section className="signal-card resonance-card">
    <div className="signal-card__header">
      <h3>{panel.title}</h3>
      <div className="signal-card__header-right">
        <span className="signal-card__count">{panel.count || 0} 只</span>
        {panel.count > 0 && panel.stocks[0]?.latest_trade_date && (
          <Link
            href={`/resonance-details?trade_date=${panel.stocks[0].latest_trade_date}&signal_side=buy&resonance_level=${panel.stocks[0].latest_resonance_level}`}
            className="resonance-detail-btn"
          >
            详情
          </Link>
        )}
      </div>
    </div>
    <StockList stocks={panel.stocks || []} />
  </section>
);

export default function SignalStatisticsPage() {
  const [dates, setDates] = useState([]);
  const [selectedDate, setSelectedDate] = useState("");
  const [panels, setPanels] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const loadStatistics = useCallback(async (tradeDate) => {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams();
      if (tradeDate) params.set("trade_date", tradeDate);
      const res = await apiFetch(`/daily-stock-signals/statistics?${params.toString()}`);
      if (!res.ok) throw new Error(`加载失败: ${res.status}`);
      const data = await res.json();
      setPanels(data.panels || []);
      if (data.trade_date) setSelectedDate(data.trade_date);
    } catch (err) {
      setError(err.message || "加载失败");
      setPanels([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const loadDates = async () => {
      try {
        const res = await apiFetch("/daily-stock-signals/dates");
        if (!res.ok) throw new Error("加载日期失败");
        const data = await res.json();
        const items = (data.items || []).map(normalizeDateValue).filter(Boolean);
        setDates(items);
        const firstDate = items[0] || "";
        if (firstDate) {
          setSelectedDate(firstDate);
          loadStatistics(firstDate);
        }
      } catch (err) {
        setError(err.message || "加载日期失败");
      }
    };
    loadDates();
  }, [loadStatistics]);

  return (
    <main className="page">
      <header className="header">
        <div>
          <p className="eyebrow">Quant Platform</p>
          <h1>强共振信号统计</h1>
          <p className="text-muted" style={{ fontSize: 14, marginTop: 4 }}>
            只统计强共振（9+）和极强共振（14+），排除普通共振
          </p>
        </div>
      </header>

      <div className="toolbar">
        <form className="toolbar__left" onSubmit={(e) => { e.preventDefault(); loadStatistics(selectedDate); }}>
          <div className="field" style={{ marginBottom: 0 }}>
            <select id="tradeDate" value={selectedDate} onChange={(e) => setSelectedDate(e.target.value)}>
              <option value="">请选择日期</option>
              {dates.map((item) => <option key={item} value={item}>{formatDate(item)}</option>)}
            </select>
          </div>
          <button className="primary" type="submit" disabled={loading}>{loading ? "..." : "查询"}</button>
        </form>
      </div>

      {error ? <div className="error">{error}</div> : null}

      <div className="signal-card-stack">
        {panels.map((panel) => (
          <StatisticsPanel key={panel.id} panel={panel} />
        ))}
      </div>
    </main>
  );
}
