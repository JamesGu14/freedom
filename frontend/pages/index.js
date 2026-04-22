import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { apiFetch } from "../lib/api";

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

const parseYmd = (value) => {
  const normalized = normalizeDateValue(value);
  if (!normalized) return null;
  return new Date(Number(normalized.slice(0, 4)), Number(normalized.slice(4, 6)) - 1, Number(normalized.slice(6, 8)));
};

const buildCalendar = (year, monthIndex) => {
  const firstDay = new Date(year, monthIndex, 1);
  const startWeekday = firstDay.getDay();
  const daysInMonth = new Date(year, monthIndex + 1, 0).getDate();
  const cells = [];
  for (let i = 0; i < startWeekday; i += 1) cells.push(null);
  for (let day = 1; day <= daysInMonth; day += 1) cells.push(new Date(year, monthIndex, day));
  while (cells.length % 7 !== 0) cells.push(null);
  return cells;
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

const SIGNAL_LABELS = {
  buy_macd_kdj_double_cross: "双金叉",
  buy_ma_bullish_formation: "均线多头形成",
  buy_volume_breakout_20d: "放量突破20日新高",
  buy_rsi_rebound: "RSI超卖回升",
  sell_macd_kdj_double_cross: "双死叉",
  sell_ma_bearish_formation: "均线空头形成",
  sell_volume_breakdown_20d: "放量跌破20日新低",
  sell_rsi_fall: "RSI超买回落",
};

const PATTERN_LABELS = {
  ma_bullish_alignment: "均线多头",
  five_ma_rising: "五线顺上",
  ascending_channel: "上升通道",
  accelerating_uptrend: "加速上涨",
  climbing_slope: "上升爬坡形",
  ma_bearish_alignment: "均线空头",
  descending_channel: "下降通道",
  platform_breakout: "突破平台",
  bollinger_breakout: "布林突破",
  ma_convergence_breakout: "均线粘合突破",
  water_lily: "出水芙蓉",
  one_yang_three_lines: "一阳穿三线",
  dragon_out_of_sea: "蛟龙出海",
  w_bottom: "W底",
  rounding_bottom: "圆弧底",
  yang_engulfs_yin: "阳包阴",
  morning_doji_star: "早晨十字星",
  double_needle_bottom: "双针探底",
  golden_needle_bottom: "金针探底",
  hammer: "锤子线",
  v_reversal: "V型反转",
  dark_cloud_cover: "乌云盖顶",
  red_three_soldiers: "红三兵",
  black_three_soldiers: "黑三兵",
  three_crows: "三只乌鸦",
  bullish_cannon: "多方炮",
  rising_sun: "旭日东升",
  limit_up_double_cannon: "涨停双响炮",
  limit_up_return_spear: "涨停回马枪",
  immortal_pointing: "仙人指路",
  old_duck_head: "老鸭头",
  air_refueling: "空中加油",
  beauty_shoulder: "美人肩",
  golden_pit: "黄金坑",
  treasure_basin: "聚宝盆",
  flag_formation: "旗形",
  one_yang_finger: "一阳指",
  desperate_counterattack: "绝地反击",
  long_upper_shadow: "长上影巨震洗盘",
  small_yang_steps: "碎布小阳",
  golden_spider: "金蜘蛛",
  long_lower_shadow: "长下影线",
  attack_forcing_line: "攻击迫线",
  bullish_vanguard: "多头尖兵",
  evening_star: "黄昏之星",
  inverted_hammer: "倒锤头",
  gap_up: "向上跳空",
  gap_down: "向下跳空",
  rounding_top: "圆顶",
  tower_top: "塔形顶",
  buy_macd_kdj_double_cross: "双金叉",
  buy_volume_breakout_20d: "放量突破",
  buy_rsi_rebound: "RSI超卖回升",
  sell_macd_kdj_double_cross: "双死叉",
  sell_volume_breakdown_20d: "放量跌破",
  sell_rsi_fall: "RSI超买回落",
};

const RESONANCE_LABELS = {
  very_strong: "极强共振 (14+)",
  strong: "强共振 (9+)",
  normal: "普通共振 (5+)",
};

const RESONANCE_ORDER = ["very_strong", "strong", "normal"];

const getSignalLabel = (t) => SIGNAL_LABELS[t] || t;
const getResonanceLabel = (l) => RESONANCE_LABELS[l] || l;
const getPatternLabel = (p) => PATTERN_LABELS[p] || p;

const PAGE_SIZE = 20;

/* ─── Stock signal popup ─── */

function StockSignalPopup({ ts_code, name, onClose }) {
  const [signals, setSignals] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await apiFetch(`/daily-stock-signals/stock/${encodeURIComponent(ts_code)}?limit_days=30`);
        if (!res.ok) throw new Error(res.status);
        const data = await res.json();
        if (!cancelled) setSignals(data.signals || []);
      } catch {
        if (!cancelled) setSignals([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [ts_code]);

  const grouped = useMemo(() => {
    const map = new Map();
    for (const row of signals) {
      const d = row.trade_date;
      if (!map.has(d)) map.set(d, { trade_date: d, stock: row.stock || {}, tags: [], sides: new Set(), next_1d_pct: row.next_1d_pct, next_5d_pct: row.next_5d_pct });
      const entry = map.get(d);
      entry.sides.add(row.signal_side);
      entry.next_1d_pct = row.next_1d_pct ?? entry.next_1d_pct;
      entry.next_5d_pct = row.next_5d_pct ?? entry.next_5d_pct;
      if (row.signal_type) {
        entry.tags.push(getSignalLabel(row.signal_type));
      } else if (row.resonance_level) {
        entry.tags.push(getResonanceLabel(row.resonance_level));
      }
      if (row.stock?.patterns?.length) {
        entry.patterns = row.stock.patterns;
      }
      if (row.stock?.weighted_score) {
        entry.weighted_score = row.stock.weighted_score;
      }
    }
    return [...map.values()];
  }, [signals]);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box" onClick={(e) => e.stopPropagation()}>
        <div className="modal-box__header">
          <h3>{name || ts_code} · 近30日信号</h3>
          <button type="button" className="modal-box__close" onClick={onClose}>✕</button>
        </div>
        <div className="modal-box__body">
          {loading ? (
            <div style={{ padding: 24, textAlign: "center", color: "var(--muted)" }}>加载中...</div>
          ) : !grouped.length ? (
            <div style={{ padding: 24, textAlign: "center", color: "var(--muted)" }}>过去 30 日无信号</div>
          ) : (
            <table className="modal-table">
              <thead>
                <tr>
                  <th>日期</th>
                  <th>信号</th>
                  <th>方向</th>
                  <th>收盘</th>
                  <th>涨跌</th>
                  <th>次日涨跌</th>
                  <th>5日涨跌</th>
                </tr>
              </thead>
              <tbody>
                {grouped.map((row) => {
                  const s = row.stock;
                  const sideLabel = [...row.sides].sort().map((x) => x === "buy" ? "买入" : "卖出").join(" / ");
                  const sideClass = row.sides.size === 1 ? ([...row.sides][0] === "buy" ? "text-red" : "text-green") : "";
                  const FwdPct = ({ value }) => {
                    if (value === null || value === undefined) return <span style={{ color: "var(--muted)" }}>尚未发生</span>;
                    return <span className={value > 0 ? "text-red" : value < 0 ? "text-green" : ""}>{formatPct(value)}</span>;
                  };
                  return (
                    <tr key={row.trade_date}>
                      <td>{formatDate(row.trade_date)}</td>
                      <td>
                        <div>{row.tags.join("、")}</div>
                        {row.patterns?.length > 0 && (
                          <div className="signal-popup-patterns">
                            {row.patterns.map((p) => (
                              <span key={p} className="signal-popup-pattern-tag">{getPatternLabel(p)}</span>
                            ))}
                          </div>
                        )}
                        {row.weighted_score && <div className="signal-popup-score">得分: {row.weighted_score}</div>}
                      </td>
                      <td className={sideClass}>{sideLabel}</td>
                      <td>{formatNumber(s.close)}</td>
                      <td className={Number(s.pct_chg) > 0 ? "text-red" : Number(s.pct_chg) < 0 ? "text-green" : ""}>{formatPct(s.pct_chg)}</td>
                      <td><FwdPct value={row.next_1d_pct} /></td>
                      <td><FwdPct value={row.next_5d_pct} /></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}

function PatternDetailPopup({ stock, tradeDate, onClose }) {
  const [details, setDetails] = useState(null);
  const [loading, setLoading] = useState(true);
  const [history, setHistory] = useState([]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [patternRes, historyRes] = await Promise.all([
          apiFetch(`/daily-stock-signals/stock/${encodeURIComponent(stock.ts_code)}/patterns?trade_date=${tradeDate}`),
          apiFetch(`/daily-stock-signals/stock/${encodeURIComponent(stock.ts_code)}?limit_days=90`),
        ]);
        const patternData = patternRes.ok ? await patternRes.json() : null;
        const historyData = historyRes.ok ? await historyRes.json() : {};
        if (!cancelled) {
          setDetails(patternData);
          setHistory(historyData.signals || []);
        }
      } catch {
        if (!cancelled) { setDetails(null); setHistory([]); }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [stock.ts_code, tradeDate]);

  const patterns = details?.patterns || stock.patterns || [];
  const weightedScore = details?.weighted_score || stock.weighted_score || 0;
  const resonanceLevel = details?.resonance_level || stock.resonance_level || "";

  const groupedPatterns = useMemo(() => {
    const groups = {};
    for (const p of patterns) {
      const cat = p.category || "其他";
      if (!groups[cat]) groups[cat] = [];
      groups[cat].push(p);
    }
    return groups;
  }, [patterns]);

  const buyHistory = useMemo(() => {
    const map = new Map();
    for (const row of history) {
      if (row.signal_side !== "buy") continue;
      const d = row.trade_date;
      if (!map.has(d)) {
        map.set(d, {
          trade_date: d,
          stock: row.stock || {},
          weighted_score: row.stock?.weighted_score,
          resonance_level: row.resonance_level,
          signal_type: row.signal_type,
          next_1d_pct: row.next_1d_pct,
          next_5d_pct: row.next_5d_pct,
          tags: [],
        });
      }
      const entry = map.get(d);
      entry.next_1d_pct = entry.next_1d_pct ?? row.next_1d_pct;
      entry.next_5d_pct = entry.next_5d_pct ?? row.next_5d_pct;
      if (row.signal_type) entry.tags.push(getSignalLabel(row.signal_type));
      if (row.resonance_level) entry.tags.push(getResonanceLabel(row.resonance_level));
      if (row.stock?.weighted_score && !entry.weighted_score) entry.weighted_score = row.stock.weighted_score;
    }
    return [...map.values()];
  }, [history]);

  const FwdPct = ({ value }) => {
    if (value === null || value === undefined) return <span style={{ color: "var(--muted)", fontSize: 11 }}>尚无数据</span>;
    return <span className={value > 0 ? "text-red" : value < 0 ? "text-green" : ""}>{formatPct(value)}</span>;
  };

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
                    {getResonanceLabel(resonanceLevel)}
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
                          {getPatternLabel(p.pattern)}
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

              {buyHistory.length > 0 && (
                <div className="pattern-history">
                  <h4 className="pattern-history__title">历史买入信号</h4>
                  <table className="modal-table">
                    <thead>
                      <tr>
                        <th>日期</th>
                        <th>信号</th>
                        <th>当日涨幅</th>
                        <th>次日涨幅</th>
                        <th>5日涨幅</th>
                      </tr>
                    </thead>
                    <tbody>
                      {buyHistory.map((row) => {
                        const s = row.stock;
                        const isCurrent = row.trade_date === tradeDate;
                        return (
                          <tr key={row.trade_date} style={isCurrent ? { background: "var(--accent-subtle)" } : undefined}>
                            <td>{formatDate(row.trade_date)}</td>
                            <td>
                              <div>{row.tags.join("、")}</div>
                              {row.weighted_score ? <div style={{ fontSize: 11, color: "var(--accent-dark)" }}>得分 {row.weighted_score}</div> : null}
                            </td>
                            <td className={Number(s.pct_chg) > 0 ? "text-red" : Number(s.pct_chg) < 0 ? "text-green" : ""}>{formatPct(s.pct_chg)}</td>
                            <td><FwdPct value={row.next_1d_pct} /></td>
                            <td><FwdPct value={row.next_5d_pct} /></td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/* ─── Stock grid ─── */

const StockList = ({ stocks = [], tradeDate = "" }) => {
  const [page, setPage] = useState(1);
  const [popupStock, setPopupStock] = useState(null);
  const [patternStock, setPatternStock] = useState(null);

  useEffect(() => { setPage(1); }, [stocks]);

  if (!stocks.length) {
    return <div className="signal-empty">当日无命中</div>;
  }

  const totalPages = Math.ceil(stocks.length / PAGE_SIZE);
  const pageItems = stocks.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  return (
    <div>
      <div className="signal-stock-grid">
        {pageItems.map((item) => (
          <div key={`${item.ts_code}-${item.signal_count || item.signal_count_same_side || item.weighted_score || 0}`} className="signal-stock-cell">
            <div className="signal-stock-cell__head">
              <span className="signal-stock-cell__name">{item.name || item.ts_code}</span>
              <span className="signal-stock-cell__code">{item.ts_code}</span>
            </div>
            <div className="signal-stock-cell__info">
              <span>{item.industry || "-"}</span>
              <span>收盘 {formatNumber(item.close)}</span>
              <span className={Number(item.pct_chg) > 0 ? "text-red" : Number(item.pct_chg) < 0 ? "text-green" : ""}>{formatPct(item.pct_chg)}</span>
              <span>量比 {formatNumber(item.volume_ratio)}</span>
            </div>
            {Array.isArray(item.signal_types) && item.signal_types.length ? (
              <div className="signal-stock-cell__tags">
                {item.signal_types.map((st) => (
                  <span key={st} className="signal-tag">{getSignalLabel(st)}</span>
                ))}
              </div>
            ) : null}
            {Array.isArray(item.patterns) && item.patterns.length ? (
              <div className="signal-stock-cell__patterns">
                <span className="signal-stock-cell__score">得分: {item.weighted_score}</span>
                <span className="signal-stock-cell__pattern-count">{item.patterns.length} 个信号</span>
              </div>
            ) : null}
            <div className="signal-stock-cell__foot">
              <span>{item.signal_count ?? item.signal_count_same_side ?? (item.weighted_score ? `${item.weighted_score}分` : "-")}</span>
              <div className="signal-stock-cell__actions">
                {Array.isArray(item.patterns) && item.patterns.length ? (
                  <button type="button" className="link-button" onClick={() => setPatternStock(item)}>详情</button>
                ) : (
                  <button type="button" className="link-button" onClick={() => setPopupStock(item)}>信号</button>
                )}
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
      {popupStock && (
        <StockSignalPopup ts_code={popupStock.ts_code} name={popupStock.name || popupStock.ts_code} onClose={() => setPopupStock(null)} />
      )}
      {patternStock && tradeDate && (
        <PatternDetailPopup stock={patternStock} tradeDate={tradeDate} onClose={() => setPatternStock(null)} />
      )}
    </div>
  );
};

/* ─── Cards ─── */

const SignalGroupButton = ({ group, onClick }) => (
  <button type="button" className="signal-group-btn" onClick={onClick}>
    <span className="signal-group-btn__label">{getSignalLabel(group.signal_type)}</span>
    <span className="signal-group-btn__count">{group.count || 0} 只</span>
  </button>
);

const ResonanceCard = ({ group }) => (
  <section className="signal-card resonance-card">
    <div className="signal-card__header">
      <h3>{getResonanceLabel(group.resonance_level)}</h3>
      <span className="signal-card__count">{group.count || 0} 只</span>
    </div>
    <StockList stocks={group.stocks || []} tradeDate={group.trade_date} />
  </section>
);



function SignalGroupPopup({ group, onClose }) {
  const [page, setPage] = useState(1);
  const stocks = group.stocks || [];
  const totalPages = Math.ceil(stocks.length / PAGE_SIZE);
  const pageItems = stocks.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box modal-box--wide" onClick={(e) => e.stopPropagation()}>
        <div className="modal-box__header">
          <h3>{getSignalLabel(group.signal_type)} · {group.count || 0} 只</h3>
          <button type="button" className="modal-box__close" onClick={onClose}>✕</button>
        </div>
        <div className="modal-box__body">
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
                  <span className={Number(item.pct_chg) > 0 ? "text-red" : Number(item.pct_chg) < 0 ? "text-green" : ""}>{formatPct(item.pct_chg)}</span>
                  <span>量比 {formatNumber(item.volume_ratio)}</span>
                </div>
                <div className="signal-stock-cell__foot">
                  <Link className="link-button" href={`/stocks/${item.ts_code}`}>K线</Link>
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
        </div>
      </div>
    </div>
  );
}

/* ─── Calendar popup ─── */

function CalendarPopup({ dateSet, selectedDate, calendarMonth, onChangeMonth, onSelect, onClose }) {
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box modal-box--calendar" onClick={(e) => e.stopPropagation()}>
        <div className="modal-box__header">
          <h3>信号日历</h3>
          <button type="button" className="modal-box__close" onClick={onClose}>✕</button>
        </div>
        <div className="modal-box__body">
          <div className="calendar-header">
            <div className="calendar-controls">
              <button type="button" className="calendar-nav-btn" onClick={() => onChangeMonth(-1)}>‹</button>
              <span>{calendarMonth.getFullYear()}年 {calendarMonth.getMonth() + 1}月</span>
              <button type="button" className="calendar-nav-btn" onClick={() => onChangeMonth(1)}>›</button>
            </div>
          </div>
          <div className="calendar-grid">
            {["日", "一", "二", "三", "四", "五", "六"].map((label) => (
              <div key={label} className="calendar-weekday">{label}</div>
            ))}
            {buildCalendar(calendarMonth.getFullYear(), calendarMonth.getMonth()).map((day, index) => {
              if (!day) return <div key={`empty-${index}`} className="calendar-cell calendar-empty"></div>;
              const key = `${day.getFullYear()}${String(day.getMonth() + 1).padStart(2, "0")}${String(day.getDate()).padStart(2, "0")}`;
              const hasSignal = dateSet.has(key);
              const isSelected = selectedDate === key;
              return (
                <div
                  key={key}
                  className={`calendar-cell${hasSignal ? " active" : ""}${isSelected ? " selected" : ""}`}
                  onClick={() => { if (hasSignal) { onSelect(key); onClose(); } }}
                  style={{ cursor: hasSignal ? "pointer" : "default" }}
                  title={formatDate(key)}
                >
                  {day.getDate()}
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}

/* ─── Regime Calendar Popup ─── */

const REGIME_COLORS = {
  bull: "#ea3943",
  lean_bull: "#ff9800",
  range: "#ffd700",
  lean_bear: "#42a5f5",
  bear: "#00a650",
};

function RegimeCalendarPopup({ regimeHistory, onClose }) {
  const [centerMonth, setCenterMonth] = useState(() => {
    const now = new Date();
    return new Date(now.getFullYear(), now.getMonth(), 1);
  });

  const regimeMap = useMemo(() => {
    const map = new Map();
    for (const item of regimeHistory) {
      if (item.trade_date) map.set(item.trade_date, item);
    }
    return map;
  }, [regimeHistory]);

  const months = useMemo(() => {
    const m = [];
    for (let i = -1; i <= 1; i += 1) {
      const d = new Date(centerMonth);
      d.setMonth(d.getMonth() + i);
      m.push(new Date(d));
    }
    return m;
  }, [centerMonth]);

  const shiftMonths = (delta) => {
    setCenterMonth((prev) => {
      const next = new Date(prev);
      next.setMonth(next.getMonth() + delta);
      return next;
    });
  };

  const renderMonth = (year, monthIndex) => {
    const cells = buildCalendar(year, monthIndex);
    return (
      <div className="regime-month" key={`${year}-${monthIndex}`}>
        <div className="regime-month__title">{year}年{monthIndex + 1}月</div>
        <div className="regime-month__grid">
          {["日", "一", "二", "三", "四", "五", "六"].map((label) => (
            <div key={label} className="regime-month__weekday">{label}</div>
          ))}
          {cells.map((day, index) => {
            if (!day) return <div key={`empty-${index}`} className="regime-month__cell regime-month__cell--empty" />;
            const key = `${day.getFullYear()}${String(day.getMonth() + 1).padStart(2, "0")}${String(day.getDate()).padStart(2, "0")}`;
            const item = regimeMap.get(key);
            const bg = item ? REGIME_COLORS[item.regime] : "transparent";
            return (
              <div
                key={key}
                className="regime-month__cell"
                style={{ backgroundColor: bg, color: bg !== "transparent" ? "#fff" : "var(--muted)", fontWeight: item ? 700 : 400 }}
                title={item ? `${formatDate(key)} ${item.regime_label_cn}` : formatDate(key)}
              >
                {day.getDate()}
              </div>
            );
          })}
        </div>
      </div>
    );
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box modal-box--regime-calendar" onClick={(e) => e.stopPropagation()}>
        <div className="modal-box__header">
          <h3>多空日历</h3>
          <button type="button" className="modal-box__close" onClick={onClose}>✕</button>
        </div>
        <div className="modal-box__body">
          <div className="regime-calendar-controls">
            <button type="button" className="calendar-nav-btn" onClick={() => shiftMonths(-1)}>‹</button>
            <span>{centerMonth.getFullYear()}年{centerMonth.getMonth() + 1}月前后</span>
            <button type="button" className="calendar-nav-btn" onClick={() => shiftMonths(1)}>›</button>
          </div>
          <div className="regime-calendar-months">
            {months.map((m) => renderMonth(m.getFullYear(), m.getMonth()))}
          </div>
          <div className="regime-legend">
            {[
              { regime: "bull", label: "牛市" },
              { regime: "lean_bull", label: "偏多" },
              { regime: "range", label: "震荡" },
              { regime: "lean_bear", label: "偏空" },
              { regime: "bear", label: "熊市" },
            ].map(({ regime, label }) => (
              <span key={regime} className="regime-legend__item">
                <span className="regime-legend__dot" style={{ backgroundColor: REGIME_COLORS[regime] }} />
                {label}
              </span>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

/* ─── Page ─── */

export default function DailyStockSignalsPage() {
  const [dates, setDates] = useState([]);
  const [dateSet, setDateSet] = useState(new Set());
  const [selectedDate, setSelectedDate] = useState("");
  const [calendarMonth, setCalendarMonth] = useState(() => {
    const now = new Date();
    return new Date(now.getFullYear(), now.getMonth(), 1);
  });
  const [showCalendar, setShowCalendar] = useState(false);
  const [overview, setOverview] = useState({
    buy_signals: [], sell_signals: [],
    buy_resonance: [], sell_resonance: [],
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [marketRegime, setMarketRegime] = useState(null);
  const [dailyRegime, setDailyRegime] = useState(null);
  const [regimeHistory, setRegimeHistory] = useState([]);
  const [showRegimeCalendar, setShowRegimeCalendar] = useState(false);
  const [signalPopupGroup, setSignalPopupGroup] = useState(null);

  const summary = useMemo(() => ({
    buySignalHits: overview.buy_signals.reduce((sum, item) => sum + Number(item.count || 0), 0),
    sellSignalHits: overview.sell_signals.reduce((sum, item) => sum + Number(item.count || 0), 0),
    buyResonanceHits: overview.buy_resonance.reduce((sum, item) => sum + Number(item.count || 0), 0),
    sellResonanceHits: overview.sell_resonance.reduce((sum, item) => sum + Number(item.count || 0), 0),
  }), [overview]);

  const loadOverview = useCallback(async (tradeDate) => {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams();
      if (tradeDate) params.set("trade_date", tradeDate);
      const res = await apiFetch(`/daily-stock-signals/overview?${params.toString()}`);
      if (!res.ok) throw new Error(`加载失败: ${res.status}`);
      const data = await res.json();
      setOverview({
        buy_signals: data.buy_signals || [],
        sell_signals: data.sell_signals || [],
        buy_resonance: data.buy_resonance || [],
        sell_resonance: data.sell_resonance || [],
      });
      if (data.trade_date) setSelectedDate(data.trade_date);
    } catch (err) {
      setError(err.message || "加载失败");
      setOverview({ buy_signals: [], sell_signals: [], buy_resonance: [], sell_resonance: [] });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const loadDates = async () => {
      try {
        const res = await apiFetch(`/daily-stock-signals/dates`);
        if (!res.ok) throw new Error(`加载日期失败: ${res.status}`);
        const data = await res.json();
        const items = (data.items || []).map(normalizeDateValue).filter(Boolean);
        setDates(items);
        setDateSet(new Set(items));
        const firstDate = items[0] || "";
        if (firstDate) {
          setSelectedDate(firstDate);
          const latest = parseYmd(firstDate);
          if (latest) setCalendarMonth(new Date(latest.getFullYear(), latest.getMonth(), 1));
          loadOverview(firstDate);
        }
      } catch (err) {
        setError(err.message || "加载日期失败");
      }
    };
    loadDates();
  }, [loadOverview]);

  useEffect(() => {
    (async () => {
      try {
        const res = await apiFetch("/market-regime/latest");
        if (res.ok) {
          const data = await res.json();
          if (data && data.trade_date) setMarketRegime(data);
        }
      } catch {}
    })();
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const res = await apiFetch("/market-regime/history?limit=2000");
        if (res.ok) {
          const data = await res.json();
          setRegimeHistory(data.items || []);
        }
      } catch {}
    })();
  }, []);

  useEffect(() => {
    if (!selectedDate) {
      setDailyRegime(null);
      return;
    }
    (async () => {
      try {
        const res = await apiFetch(`/market-regime/by-date?trade_date=${selectedDate}`);
        if (res.ok) {
          const data = await res.json();
          setDailyRegime(data && data.trade_date ? data : null);
        }
      } catch {
        setDailyRegime(null);
      }
    })();
  }, [selectedDate]);

  const changeMonth = (delta) => {
    const next = new Date(calendarMonth);
    next.setMonth(next.getMonth() + delta);
    setCalendarMonth(next);
  };

  const sortedBuyResonance = useMemo(
    () => [...overview.buy_resonance].sort((a, b) => RESONANCE_ORDER.indexOf(a.resonance_level) - RESONANCE_ORDER.indexOf(b.resonance_level)),
    [overview.buy_resonance],
  );
  const sortedSellResonance = useMemo(
    () => [...overview.sell_resonance].sort((a, b) => RESONANCE_ORDER.indexOf(a.resonance_level) - RESONANCE_ORDER.indexOf(b.resonance_level)),
    [overview.sell_resonance],
  );

  return (
    <main className="page">
      <header className="header">
        <div>
          <p className="eyebrow">Quant Platform</p>
          <h1>Daily Stock Signals</h1>
        </div>
      </header>

      {marketRegime && (
        <div className={`regime-banner regime-banner--${marketRegime.regime}`}>
          <span className="regime-banner__label">{marketRegime.regime_label_cn}</span>
          <span className="regime-banner__meta">
            上证 {formatNumber(marketRegime.close)} {formatPct(marketRegime.pct_change)}
          </span>
          <span className="regime-banner__meta">
            综合得分 {Number(marketRegime.total_score).toFixed(1)}
          </span>
          <span className="regime-banner__meta">
            上涨占比 {formatPct((marketRegime.breadth_detail?.up_ratio || 0) * 100)}
          </span>
          <span className="regime-banner__date">{formatDate(marketRegime.trade_date)}</span>
        </div>
      )}

      <div className="toolbar">
        <form className="toolbar__left" onSubmit={(e) => { e.preventDefault(); loadOverview(selectedDate); }}>
          <div className="field" style={{ marginBottom: 0 }}>
            <select id="tradeDate" value={selectedDate} onChange={(e) => setSelectedDate(e.target.value)}>
              <option value="">请选择日期</option>
              {dates.map((item) => <option key={item} value={item}>{formatDate(item)}</option>)}
            </select>
          </div>
          <button type="button" className="calendar-toggle-btn" disabled={dates.indexOf(selectedDate) >= dates.length - 1} onClick={() => { const d = dates[dates.indexOf(selectedDate) + 1]; if (d) { setSelectedDate(d); loadOverview(d); } }}>‹</button>
          <button className="primary" type="submit" disabled={loading}>{loading ? "..." : "查询"}</button>
          <button type="button" className="calendar-toggle-btn" disabled={dates.indexOf(selectedDate) <= 0} onClick={() => { const d = dates[dates.indexOf(selectedDate) - 1]; if (d) { setSelectedDate(d); loadOverview(d); } }}>›</button>
          <button type="button" className="calendar-toggle-btn" onClick={() => setShowCalendar(true)}>日历</button>
          {dailyRegime && (
            <span className={`toolbar-regime toolbar-regime--${dailyRegime.regime}`} title={`大盘状态: ${dailyRegime.regime_label_cn} 得分 ${Number(dailyRegime.total_score).toFixed(1)}`}>
              {dailyRegime.regime_label_cn} · {Number(dailyRegime.total_score).toFixed(1)}
            </span>
          )}
          <button type="button" className="calendar-toggle-btn regime-calendar-btn" onClick={() => setShowRegimeCalendar(true)}>多空日历</button>
        </form>
        <div className="toolbar__right">
          <div className="summary-inline">
            <span className="summary-pill" title="买入命中">买入 <strong>{summary.buySignalHits}</strong></span>
            <span className="summary-pill" title="卖出命中">卖出 <strong>{summary.sellSignalHits}</strong></span>
            <span className="summary-pill" title="买入共振">买共振 <strong>{summary.buyResonanceHits}</strong></span>
            <span className="summary-pill" title="卖出共振">卖共振 <strong>{summary.sellResonanceHits}</strong></span>
          </div>
        </div>
      </div>

      {error ? <div className="error">{error}</div> : null}

      <section className="signal-section-grid">
        <div>
          <h2 className="section-title section-title--buy">📈 买入共振</h2>
          <div className="signal-card-stack">
            {sortedBuyResonance.map((group) => <ResonanceCard key={`${group.signal_side}-${group.resonance_level}`} group={group} />)}
          </div>
        </div>
        <div>
          <h2 className="section-title section-title--sell">📉 卖出共振</h2>
          <div className="signal-card-stack">
            {sortedSellResonance.map((group) => <ResonanceCard key={`${group.signal_side}-${group.resonance_level}`} group={group} />)}
          </div>
        </div>
      </section>

      <section className="signal-section-grid">
        <div>
          <h2 className="section-title section-title--buy">📈 买入信号</h2>
          <div className="signal-btn-stack">
            {overview.buy_signals.map((group) => (
              <SignalGroupButton key={group.signal_type} group={group} onClick={() => setSignalPopupGroup(group)} />
            ))}
          </div>
        </div>
        <div>
          <h2 className="section-title section-title--sell">📉 卖出信号</h2>
          <div className="signal-btn-stack">
            {overview.sell_signals.map((group) => (
              <SignalGroupButton key={group.signal_type} group={group} onClick={() => setSignalPopupGroup(group)} />
            ))}
          </div>
        </div>
      </section>

      {signalPopupGroup && (
        <SignalGroupPopup group={signalPopupGroup} onClose={() => setSignalPopupGroup(null)} />
      )}

      {showCalendar && (
        <CalendarPopup
          dateSet={dateSet}
          selectedDate={selectedDate}
          calendarMonth={calendarMonth}
          onChangeMonth={changeMonth}
          onSelect={(key) => { setSelectedDate(key); loadOverview(key); }}
          onClose={() => setShowCalendar(false)}
        />
      )}
      {showRegimeCalendar && (
        <RegimeCalendarPopup
          regimeHistory={regimeHistory}
          onClose={() => setShowRegimeCalendar(false)}
        />
      )}
    </main>
  );
}
