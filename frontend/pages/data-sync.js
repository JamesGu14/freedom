import { useEffect, useMemo, useState } from "react";
import { apiFetch } from "../lib/api";
import { useAuth } from "../lib/auth";

const STATUS_LABEL = {
  synced_all_required: "已同步",
  partially_synced: "部分缺失",
  missing: "未同步",
  non_trading: "非交易日",
};

const WEEKDAY_LABELS = ["日", "一", "二", "三", "四", "五", "六"];

const toInputDate = (value) => {
  const text = String(value || "").replace(/-/g, "");
  if (text.length !== 8) return "";
  return `${text.slice(0, 4)}-${text.slice(4, 6)}-${text.slice(6, 8)}`;
};

const fromInputDate = (value) => String(value || "").replace(/-/g, "");

const formatYmd = (value) => {
  const text = String(value || "").replace(/-/g, "");
  if (text.length !== 8) return String(value || "-");
  return `${text.slice(0, 4)}-${text.slice(4, 6)}-${text.slice(6, 8)}`;
};

const parseInputDate = (value) => {
  if (!value) return null;
  const date = new Date(`${value}T00:00:00`);
  return Number.isNaN(date.getTime()) ? null : date;
};

const buildMonthCells = (year, monthIndex) => {
  const first = new Date(year, monthIndex, 1);
  const startWeekday = first.getDay();
  const days = new Date(year, monthIndex + 1, 0).getDate();
  const cells = [];
  for (let i = 0; i < startWeekday; i += 1) cells.push(null);
  for (let day = 1; day <= days; day += 1) cells.push(new Date(year, monthIndex, day));
  while (cells.length % 7 !== 0) cells.push(null);
  return cells;
};

const dateToYmd = (date) => {
  const y = date.getFullYear();
  const m = `${date.getMonth() + 1}`.padStart(2, "0");
  const d = `${date.getDate()}`.padStart(2, "0");
  return `${y}${m}${d}`;
};

const statusClass = (status) => {
  if (status === "synced_all_required") return "sync-status sync-status--ok";
  if (status === "partially_synced") return "sync-status sync-status--partial";
  if (status === "missing") return "sync-status sync-status--missing";
  if (status === "non_trading") return "sync-status sync-status--nontrading";
  return "sync-status";
};

const badgeClass = (status) => {
  if (status === "synced_all_required" || status === "synced") return "badge sync-badge sync-badge--ok";
  if (status === "partially_synced") return "badge sync-badge sync-badge--partial";
  if (status === "missing") return "badge sync-badge sync-badge--missing";
  if (status === "non_trading") return "badge sync-badge sync-badge--nontrading";
  return "badge";
};

const buildMonthPanels = (startDate, endDate) => {
  const start = parseInputDate(startDate);
  const end = parseInputDate(endDate);
  if (!start || !end || start > end) return [];
  const cursor = new Date(start.getFullYear(), start.getMonth(), 1);
  const last = new Date(end.getFullYear(), end.getMonth(), 1);
  const panels = [];
  while (cursor <= last) {
    const year = cursor.getFullYear();
    const monthIndex = cursor.getMonth();
    const month = `${year}${`${monthIndex + 1}`.padStart(2, "0")}`;
    panels.push({
      month,
      monthLabel: `${year}-${`${monthIndex + 1}`.padStart(2, "0")}`,
      cells: buildMonthCells(year, monthIndex),
    });
    cursor.setMonth(cursor.getMonth() + 1);
  }
  return panels;
};

export default function DataSyncPage() {
  const { roles } = useAuth();
  const isAdmin = Array.isArray(roles) && roles.some((role) => String(role).trim().toLowerCase() === "admin");

  const today = useMemo(() => {
    const now = new Date();
    return `${now.getFullYear()}-${`${now.getMonth() + 1}`.padStart(2, "0")}-${`${now.getDate()}`.padStart(2, "0")}`;
  }, []);

  const defaultStart = useMemo(() => {
    const now = new Date();
    now.setMonth(now.getMonth() - 5);
    return `${now.getFullYear()}-${`${now.getMonth() + 1}`.padStart(2, "0")}-${`${now.getDate()}`.padStart(2, "0")}`;
  }, []);

  const [startDate, setStartDate] = useState(defaultStart);
  const [endDate, setEndDate] = useState(today);
  const [calendar, setCalendar] = useState([]);
  const [summary, setSummary] = useState(null);
  const [requiredTasks, setRequiredTasks] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [selectedItem, setSelectedItem] = useState(null);

  const calendarMap = useMemo(() => {
    const map = new Map();
    for (const item of calendar) {
      map.set(item.trade_date, item);
    }
    return map;
  }, [calendar]);

  const monthPanels = useMemo(() => buildMonthPanels(startDate, endDate), [startDate, endDate]);

  const loadCalendar = async () => {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams();
      params.set("start_date", fromInputDate(startDate));
      params.set("end_date", fromInputDate(endDate));
      const res = await apiFetch(`/data-sync/calendar?${params.toString()}`);
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        throw new Error(detail.detail || `加载失败: ${res.status}`);
      }
      const data = await res.json();
      setCalendar(data.items || []);
      setSummary(data.summary || null);
      setRequiredTasks(data.required_tasks || []);
      setSelectedItem(null);
    } catch (err) {
      setError(err.message || "加载失败");
      setCalendar([]);
      setSummary(null);
      setRequiredTasks([]);
      setSelectedItem(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!isAdmin) return;
    loadCalendar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAdmin]);

  if (!isAdmin) {
    return (
      <main className="page">
        <header className="header">
          <div>
            <p className="eyebrow">Admin</p>
            <h1>数据同步</h1>
            <p className="subtitle">仅 admin 可访问</p>
          </div>
        </header>
        <section className="panel">
          <p className="empty">你没有权限访问此页面。</p>
        </section>
      </main>
    );
  }

  return (
    <main className="page">
      <header className="header">
        <div>
          <p className="eyebrow">Admin</p>
          <h1>数据同步</h1>
          <p className="subtitle">Airflow 每日同步状态总览，按接口检查每个交易日是否完整。</p>
        </div>
      </header>

      <form className="filters" onSubmit={(event) => { event.preventDefault(); loadCalendar(); }}>
        <label className="field">
          <span>开始日期</span>
          <input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} />
        </label>
        <label className="field">
          <span>结束日期</span>
          <input type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} />
        </label>
        <button className="primary" type="submit" disabled={loading}>
          {loading ? "加载中..." : "刷新状态"}
        </button>
      </form>

      {error ? <div className="error">{error}</div> : null}

      {summary ? (
        <section className="sync-summary-grid">
          <div className="kpi-tile"><div className="kpi-tile__label">交易日</div><div className="kpi-tile__value">{summary.trading_days}</div></div>
          <div className="kpi-tile"><div className="kpi-tile__label">已同步</div><div className="kpi-tile__value">{summary.synced_all_required}</div></div>
          <div className="kpi-tile"><div className="kpi-tile__label">部分缺失</div><div className="kpi-tile__value">{summary.partially_synced}</div></div>
          <div className="kpi-tile"><div className="kpi-tile__label">未同步</div><div className="kpi-tile__value">{summary.missing}</div></div>
          <div className="kpi-tile"><div className="kpi-tile__label">非交易日</div><div className="kpi-tile__value">{summary.non_trading}</div></div>
        </section>
      ) : null}

      <section className="panel sync-legend">
        <span className="badge sync-badge sync-badge--ok">绿色：完整</span>
        <span className="badge sync-badge sync-badge--partial">黄色：有缺失</span>
        <span className="badge sync-badge sync-badge--missing">红色：未同步</span>
        <span className="badge sync-badge sync-badge--nontrading">灰色：非交易日</span>
      </section>

      {requiredTasks.length > 0 ? (
        <section className="panel">
          <h2>每日检查接口</h2>
          <div className="sync-task-chip-list">
            {requiredTasks.map((task) => (
              <span key={task.task} className="badge">{task.label}</span>
            ))}
          </div>
        </section>
      ) : null}

      {monthPanels.length > 0 ? (
        <section className="panel">
          <h2>日历总览</h2>
          <p className="subtitle">点击日期可以查看该日缺失了哪些接口数据。</p>
          <div className="sync-months">
            {monthPanels.map((panel) => (
              <div key={panel.month} className="panel sync-month-panel">
                <h3>{panel.monthLabel}</h3>
                <div className="calendar-grid sync-calendar-grid">
                  {WEEKDAY_LABELS.map((w) => (
                    <div key={`${panel.monthLabel}-${w}`} className="calendar-weekday">{w}</div>
                  ))}
                  {panel.cells.map((cell, idx) => {
                    if (!cell) {
                      return <div key={`${panel.monthLabel}-empty-${idx}`} className="calendar-cell calendar-empty" />;
                    }
                    const ymd = dateToYmd(cell);
                    const item = calendarMap.get(ymd);
                    const title = item
                      ? `${formatYmd(ymd)} ${STATUS_LABEL[item.status] || item.status}`
                      : `${formatYmd(ymd)} 无状态`;
                    return (
                      <button
                        key={`${panel.monthLabel}-${ymd}`}
                        type="button"
                        className={`calendar-cell sync-calendar-cell-button ${statusClass(item?.status)}`}
                        title={title}
                        onClick={() => item && setSelectedItem(item)}
                        disabled={!item}
                      >
                        <span className="sync-day">{cell.getDate()}</span>
                      </button>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      {selectedItem ? (
        <div className="modal-backdrop" onClick={() => setSelectedItem(null)} role="presentation">
          <section className="modal-card sync-detail-modal" onClick={(event) => event.stopPropagation()} role="dialog" aria-modal="true">
            <div className="modal-header">
              <div>
                <p className="eyebrow">Sync Detail</p>
                <h2>{formatYmd(selectedItem.trade_date)}</h2>
              </div>
              <button className="ghost" type="button" onClick={() => setSelectedItem(null)}>
                关闭
              </button>
            </div>

            <div className="sync-detail-summary">
              <span className={badgeClass(selectedItem.status)}>{STATUS_LABEL[selectedItem.status] || selectedItem.status}</span>
              {selectedItem.is_open ? (
                <span className="badge">完成 {selectedItem.completed_required_tasks?.length || 0} / {requiredTasks.length}</span>
              ) : (
                <span className="badge">该日非交易日</span>
              )}
            </div>

            {selectedItem.is_open && selectedItem.missing_required_task_labels?.length ? (
              <div className="sync-detail-section">
                <h3>缺失接口</h3>
                <div className="sync-task-chip-list">
                  {selectedItem.missing_required_task_labels.map((label) => (
                    <span key={label} className="badge sync-badge sync-badge--partial">{label}</span>
                  ))}
                </div>
              </div>
            ) : null}

            {selectedItem.is_open && selectedItem.completed_required_task_labels?.length ? (
              <div className="sync-detail-section">
                <h3>已完成接口</h3>
                <div className="sync-task-chip-list">
                  {selectedItem.completed_required_task_labels.map((label) => (
                    <span key={label} className="badge sync-badge sync-badge--ok">{label}</span>
                  ))}
                </div>
              </div>
            ) : null}

            {selectedItem.task_statuses?.length ? (
              <div className="sync-detail-section">
                <h3>接口明细</h3>
                <div className="sync-detail-task-list">
                  {selectedItem.task_statuses.map((task) => (
                    <div key={task.task} className="sync-detail-task-row">
                      <span>{task.label}</span>
                      <span className={badgeClass(task.status)}>{task.status === "synced" ? "已完成" : "缺失"}</span>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </section>
        </div>
      ) : null}
    </main>
  );
}
