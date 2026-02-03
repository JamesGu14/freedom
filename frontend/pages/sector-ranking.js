import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { apiFetch } from "../lib/api";

const formatDate = (value) => {
  if (!value || String(value).length !== 8) return value || "-";
  const s = String(value);
  return `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}`;
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

const getLevelLabel = (level) => {
  if (level === 1) return "一级行业";
  if (level === 2) return "二级行业";
  if (level === 3) return "三级行业";
  return "";
};

export default function SectorRanking() {
  const [level, setLevel] = useState(1);
  const [historyData, setHistoryData] = useState([]);
  const [avgData, setAvgData] = useState({
    trade_dates: [],
    strongest: [],
    weakest: [],
  });
  const [loading, setLoading] = useState(false);
  const [avgLoading, setAvgLoading] = useState(false);
  const [error, setError] = useState("");

  const topBottomN = useMemo(() => (level === 1 ? 5 : 10), [level]);

  const loadHistory = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams();
      params.set("days", "5");
      params.set("level", String(level));
      params.set("top_n", String(topBottomN));
      params.set("bottom_n", String(topBottomN));
      const res = await apiFetch(`/sector-ranking/history?${params.toString()}`);
      if (!res.ok) throw new Error(`加载失败: ${res.status}`);
      const data = await res.json();
      setHistoryData(data.data || []);
    } catch (err) {
      setHistoryData([]);
      setError(err.message || "加载失败");
    } finally {
      setLoading(false);
    }
  }, [level, topBottomN]);

  const loadAvg = useCallback(async () => {
    setAvgLoading(true);
    try {
      const params = new URLSearchParams();
      params.set("level", String(level));
      params.set("top_n", "10");
      params.set("bottom_n", "10");
      const res = await apiFetch(`/sector-ranking/avg?${params.toString()}`);
      if (!res.ok) throw new Error(`加载失败: ${res.status}`);
      const data = await res.json();
      setAvgData({
        trade_dates: data.trade_dates || [],
        strongest: data.strongest || [],
        weakest: data.weakest || [],
      });
    } catch (err) {
      setAvgData({ trade_dates: [], strongest: [], weakest: [] });
    } finally {
      setAvgLoading(false);
    }
  }, [level]);

  useEffect(() => {
    loadHistory();
    loadAvg();
  }, [loadHistory, loadAvg]);

  const levelOptions = [1, 2, 3];
  const latestDate = historyData[0]?.trade_date;

  return (
    <main className="page sector-ranking-page">
      <header className="header ranking-header">
        <div>
          <p className="eyebrow">Quant Platform</p>
          <h1>板块排名</h1>
          <p className="subtitle">
            {getLevelLabel(level)}涨跌幅排名（最近 5 个交易日）
          </p>
        </div>
        <div className="ranking-controls">
          {levelOptions.map((item) => (
            <button
              key={item}
              type="button"
              className={`level-tab ${level === item ? "active" : ""}`}
              onClick={() => setLevel(item)}
            >
              {getLevelLabel(item)}
            </button>
          ))}
        </div>
      </header>

      {error ? <div className="error">{error}</div> : null}

      <section className="ranking-section">
        <div className="section-title">
          <h2>近 5 日排名</h2>
          <span className="muted">
            {latestDate ? `最新交易日：${formatDate(latestDate)}` : "暂无数据"}
          </span>
        </div>
        {loading && historyData.length === 0 ? (
          <div className="loading-container">
            <div className="spinner"></div>
            <p>加载中...</p>
          </div>
        ) : historyData.length === 0 ? (
          <div className="empty">暂无排名数据</div>
        ) : (
          <div className="ranking-grid">
            {historyData.map((day) => (
              <div className="ranking-card" key={day.trade_date}>
                <div className="ranking-card-header">
                  <h3>{formatDate(day.trade_date)}</h3>
                  <span className="muted">Top/Bottom {topBottomN}</span>
                </div>
                <div className="ranking-card-body">
                  <div className="ranking-list">
                    <div className="ranking-list-title">涨幅前 {topBottomN}</div>
                    {day.top?.map((item, index) => (
                      <div className="ranking-item" key={`${item.ts_code}-top-${index}`}>
                        <span className="ranking-rank">{item.rank ?? "-"}</span>
                        <Link
                          className="ranking-name"
                          href={`/sectors/${item.ts_code}`}
                        >
                          {item.name || item.ts_code}
                        </Link>
                        <span className={`change-pill ${getChangeClass(item.pct_change)}`}>
                          {formatPct(item.pct_change)}
                        </span>
                      </div>
                    ))}
                  </div>
                  <div className="ranking-list">
                    <div className="ranking-list-title">跌幅前 {topBottomN}</div>
                    {day.bottom?.map((item, index) => (
                      <div
                        className="ranking-item"
                        key={`${item.ts_code}-bottom-${index}`}
                      >
                        <span className="ranking-rank">{item.rank ?? "-"}</span>
                        <Link
                          className="ranking-name"
                          href={`/sectors/${item.ts_code}`}
                        >
                          {item.name || item.ts_code}
                        </Link>
                        <span className={`change-pill ${getChangeClass(item.pct_change)}`}>
                          {formatPct(item.pct_change)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="ranking-section">
        <div className="section-title">
          <h2>5 日平均排名</h2>
          <span className="muted">
            {avgData.trade_dates.length
              ? `统计区间：${formatDate(avgData.trade_dates[0])} ~ ${formatDate(
                  avgData.trade_dates[avgData.trade_dates.length - 1]
                )}`
              : "暂无数据"}
          </span>
        </div>
        {avgLoading && avgData.strongest.length === 0 ? (
          <div className="loading-container">
            <div className="spinner"></div>
            <p>加载中...</p>
          </div>
        ) : (
          <div className="avg-panels">
            <div className="table-wrap avg-panel">
              <div className="avg-panel-header">持续强势板块（平均排名最小）</div>
              <table>
                <thead>
                  <tr>
                    <th>排名</th>
                    <th>板块</th>
                    <th className="th-numeric">平均</th>
                    <th className="th-numeric">D1</th>
                    <th className="th-numeric">D2</th>
                    <th className="th-numeric">D3</th>
                    <th className="th-numeric">D4</th>
                    <th className="th-numeric">D5</th>
                    <th className="th-numeric">5日累计</th>
                  </tr>
                </thead>
                <tbody>
                  {avgData.strongest.length === 0 ? (
                    <tr>
                      <td colSpan="9" className="empty">
                        暂无数据
                      </td>
                    </tr>
                  ) : (
                    avgData.strongest.map((item, index) => (
                      <tr key={`${item.ts_code}-strong-${index}`}>
                        <td>{index + 1}</td>
                        <td>
                          <Link
                            className="ranking-name"
                            href={`/sectors/${item.ts_code}`}
                          >
                            {item.name || item.ts_code}
                          </Link>
                        </td>
                        <td className="th-numeric">{item.rank_avg?.toFixed(2)}</td>
                        <td className="th-numeric">{item.rank_day1 ?? "-"}</td>
                        <td className="th-numeric">{item.rank_day2 ?? "-"}</td>
                        <td className="th-numeric">{item.rank_day3 ?? "-"}</td>
                        <td className="th-numeric">{item.rank_day4 ?? "-"}</td>
                        <td className="th-numeric">{item.rank_day5 ?? "-"}</td>
                        <td className="th-numeric">
                          <span
                            className={`change-pill change-pill-sm ${getChangeClass(
                              item.pct_sum
                            )}`}
                          >
                            {formatPct(item.pct_sum)}
                          </span>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            <div className="table-wrap avg-panel">
              <div className="avg-panel-header">持续弱势板块（平均排名最大）</div>
              <table>
                <thead>
                  <tr>
                    <th>排名</th>
                    <th>板块</th>
                    <th className="th-numeric">平均</th>
                    <th className="th-numeric">D1</th>
                    <th className="th-numeric">D2</th>
                    <th className="th-numeric">D3</th>
                    <th className="th-numeric">D4</th>
                    <th className="th-numeric">D5</th>
                    <th className="th-numeric">5日累计</th>
                  </tr>
                </thead>
                <tbody>
                  {avgData.weakest.length === 0 ? (
                    <tr>
                      <td colSpan="9" className="empty">
                        暂无数据
                      </td>
                    </tr>
                  ) : (
                    avgData.weakest.map((item, index) => (
                      <tr key={`${item.ts_code}-weak-${index}`}>
                        <td>{index + 1}</td>
                        <td>
                          <Link
                            className="ranking-name"
                            href={`/sectors/${item.ts_code}`}
                          >
                            {item.name || item.ts_code}
                          </Link>
                        </td>
                        <td className="th-numeric">{item.rank_avg?.toFixed(2)}</td>
                        <td className="th-numeric">{item.rank_day1 ?? "-"}</td>
                        <td className="th-numeric">{item.rank_day2 ?? "-"}</td>
                        <td className="th-numeric">{item.rank_day3 ?? "-"}</td>
                        <td className="th-numeric">{item.rank_day4 ?? "-"}</td>
                        <td className="th-numeric">{item.rank_day5 ?? "-"}</td>
                        <td className="th-numeric">
                          <span
                            className={`change-pill change-pill-sm ${getChangeClass(
                              item.pct_sum
                            )}`}
                          >
                            {formatPct(item.pct_sum)}
                          </span>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </section>
    </main>
  );
}
