import { useEffect, useMemo, useState } from "react";
import { apiFetch } from "../lib/api";
import { useAuth } from "../lib/auth";

const STATUS_LABEL = {
  synced_all_required: "已同步",
  partially_synced: "部分同步",
  missing: "缺失",
  non_trading: "非交易日",
  running: "运行中",
  pending: "排队中",
  success: "成功",
  failed: "失败",
  cancelled: "已停止",
};

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
  const text = String(value).trim();
  if (!text) return null;
  const d = new Date(`${text}T00:00:00`);
  if (Number.isNaN(d.getTime())) return null;
  return d;
};

const diffDaysInclusive = (start, end) => {
  const s = parseInputDate(start);
  const e = parseInputDate(end);
  if (!s || !e) return null;
  const ms = e.getTime() - s.getTime();
  return Math.floor(ms / (24 * 60 * 60 * 1000)) + 1;
};

const dateToYmd = (date) => {
  const y = date.getFullYear();
  const m = `${date.getMonth() + 1}`.padStart(2, "0");
  const d = `${date.getDate()}`.padStart(2, "0");
  return `${y}${m}${d}`;
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

const statusClass = (status) => {
  if (status === "synced_all_required") return "sync-status sync-status--ok";
  if (status === "partially_synced") return "sync-status sync-status--partial";
  if (status === "missing") return "sync-status sync-status--missing";
  if (status === "non_trading") return "sync-status sync-status--nontrading";
  return "sync-status";
};

export default function DataSyncPage() {
  const { username } = useAuth();
  const isAdmin = ["admin", "james"].includes(String(username || "").trim().toLowerCase());

  const today = useMemo(() => {
    const now = new Date();
    return `${now.getFullYear()}-${`${now.getMonth() + 1}`.padStart(2, "0")}-${`${now.getDate()}`.padStart(2, "0")}`;
  }, []);
  const defaultStart = today;

  const [startDate, setStartDate] = useState(defaultStart);
  const [endDate, setEndDate] = useState(today);
  const [calendar, setCalendar] = useState([]);
  const [summary, setSummary] = useState(null);
  const [missingItems, setMissingItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const [jobStartDate, setJobStartDate] = useState(defaultStart);
  const [jobEndDate, setJobEndDate] = useState(today);
  const [job, setJob] = useState(null);
  const [jobId, setJobId] = useState("");
  const [jobError, setJobError] = useState("");
  const [logs, setLogs] = useState("");
  const [logOffset, setLogOffset] = useState(0);

  const calendarMap = useMemo(() => {
    const map = new Map();
    for (const item of calendar) {
      map.set(item.trade_date, item);
    }
    return map;
  }, [calendar]);

  const missingByMonth = useMemo(() => {
    const map = new Map();
    for (const item of missingItems) {
      const key = String(item.trade_date || "").slice(0, 6);
      if (!map.has(key)) map.set(key, []);
      map.get(key).push(item);
    }
    return [...map.entries()].sort((a, b) => String(a[0]).localeCompare(String(b[0])));
  }, [missingItems]);

  const missingMonthPanels = useMemo(
    () =>
      missingByMonth.map(([month, items]) => {
        const year = Number(month.slice(0, 4));
        const monthIndex = Number(month.slice(4, 6)) - 1;
        return {
          month,
          monthLabel: `${month.slice(0, 4)}-${month.slice(4, 6)}`,
          cells: buildMonthCells(year, monthIndex),
          items,
        };
      }),
    [missingByMonth]
  );

  const loadCalendar = async () => {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams();
      params.set("start_date", fromInputDate(startDate));
      params.set("end_date", fromInputDate(endDate));

      const [calendarRes, missingRes] = await Promise.all([
        apiFetch(`/data-sync/calendar?${params.toString()}`),
        apiFetch(`/data-sync/missing?${params.toString()}`),
      ]);
      if (!calendarRes.ok) {
        const detail = await calendarRes.json().catch(() => ({}));
        throw new Error(detail.detail || `加载失败: ${calendarRes.status}`);
      }
      if (!missingRes.ok) {
        const detail = await missingRes.json().catch(() => ({}));
        throw new Error(detail.detail || `加载失败: ${missingRes.status}`);
      }
      const calendarData = await calendarRes.json();
      const missingData = await missingRes.json();
      setCalendar(calendarData.items || []);
      setSummary(calendarData.summary || null);
      setMissingItems(missingData.items || []);
    } catch (err) {
      setError(err.message || "加载失败");
      setCalendar([]);
      setSummary(null);
      setMissingItems([]);
    } finally {
      setLoading(false);
    }
  };

  const loadJob = async (nextJobId) => {
    if (!nextJobId) return;
    const res = await apiFetch(`/data-sync/jobs/${nextJobId}`);
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}));
      throw new Error(detail.detail || `任务加载失败: ${res.status}`);
    }
    const data = await res.json();
    setJob(data);
  };

  const loadJobLogs = async (nextJobId, nextOffset) => {
    if (!nextJobId) return;
    const params = new URLSearchParams();
    params.set("offset", String(nextOffset || 0));
    const res = await apiFetch(`/data-sync/jobs/${nextJobId}/logs?${params.toString()}`);
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}));
      throw new Error(detail.detail || `日志加载失败: ${res.status}`);
    }
    const data = await res.json();
    const chunk = String(data.content || "");
    if (chunk) {
      setLogs((prev) => prev + chunk);
    }
    setLogOffset(Number(data.next_offset || nextOffset || 0));
  };

  const createJob = async (event) => {
    event.preventDefault();
    setJobError("");
    try {
      const spanDays = diffDaysInclusive(jobStartDate, jobEndDate);
      if (spanDays === null) {
        throw new Error("请输入有效的开始和结束日期");
      }
      if (spanDays < 1) {
        throw new Error("开始日期不能晚于结束日期");
      }
      if (spanDays > 5) {
        throw new Error("执行同步任务最多只能选择 5 天范围");
      }
      const res = await apiFetch("/data-sync/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          start_date: fromInputDate(jobStartDate),
          end_date: fromInputDate(jobEndDate),
        }),
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        throw new Error(detail.detail || `创建任务失败: ${res.status}`);
      }
      const data = await res.json();
      const nextJobId = String(data.job_id || "");
      setJob(data);
      setJobId(nextJobId);
      setLogs("");
      setLogOffset(0);
      await loadJobLogs(nextJobId, 0);
      await loadCalendar();
    } catch (err) {
      setJobError(err.message || "创建任务失败");
    }
  };

  const stopJob = async () => {
    if (!jobId) return;
    setJobError("");
    try {
      const res = await apiFetch(`/data-sync/jobs/${jobId}/stop`, { method: "POST" });
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        throw new Error(detail.detail || `停止任务失败: ${res.status}`);
      }
      const data = await res.json();
      setJob(data);
      await loadJobLogs(jobId, logOffset);
    } catch (err) {
      setJobError(err.message || "停止任务失败");
    }
  };

  useEffect(() => {
    if (!isAdmin) return;
    loadCalendar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAdmin]);

  useEffect(() => {
    if (!jobId) return;
    const status = String(job?.status || "");
    if (!["pending", "running"].includes(status)) return;

    const timer = setInterval(async () => {
      try {
        await loadJob(jobId);
        await loadJobLogs(jobId, logOffset);
      } catch (err) {
        setJobError(err.message || "任务轮询失败");
      }
    }, 2500);
    return () => clearInterval(timer);
  }, [jobId, job?.status, logOffset]);

  useEffect(() => {
    const status = String(job?.status || "");
    if (!jobId || !["success", "failed"].includes(status)) return;
    loadCalendar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId, job?.status]);

  if (!isAdmin) {
    return (
      <main className="page">
        <header className="header">
          <div>
            <p className="eyebrow">Admin</p>
            <h1>数据同步</h1>
            <p className="subtitle">仅 admin/james 可访问</p>
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
          <p className="subtitle">交易日同步状态总览 + 手动执行 daily.sh</p>
        </div>
      </header>

      <form className="filters" onSubmit={(e) => { e.preventDefault(); loadCalendar(); }}>
        <label className="field">
          <span>开始日期</span>
          <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
        </label>
        <label className="field">
          <span>结束日期</span>
          <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
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
          <div className="kpi-tile"><div className="kpi-tile__label">部分同步</div><div className="kpi-tile__value">{summary.partially_synced}</div></div>
          <div className="kpi-tile"><div className="kpi-tile__label">缺失</div><div className="kpi-tile__value">{summary.missing}</div></div>
          <div className="kpi-tile"><div className="kpi-tile__label">非交易日</div><div className="kpi-tile__value">{summary.non_trading}</div></div>
        </section>
      ) : null}

      <section className="panel sync-legend">
        <span className="badge sync-badge sync-badge--ok">已同步</span>
        <span className="badge sync-badge sync-badge--partial">部分同步</span>
        <span className="badge sync-badge sync-badge--missing">缺失</span>
        <span className="badge sync-badge sync-badge--nontrading">非交易日</span>
      </section>

      {missingMonthPanels.length > 0 ? (
        <section className="panel">
          <h2>缺失日期详情</h2>
          <div className="sync-months">
            {missingMonthPanels.map((panel) => (
              <div key={panel.month} className="panel sync-month-panel">
                <h3>{panel.monthLabel}</h3>
                <div className="calendar-grid sync-calendar-grid">
                  {["日", "一", "二", "三", "四", "五", "六"].map((w) => (
                    <div key={`${panel.monthLabel}-${w}`} className="calendar-weekday">{w}</div>
                  ))}
                  {panel.cells.map((cell, idx) => {
                    if (!cell) return <div key={`${panel.monthLabel}-empty-${idx}`} className="calendar-cell calendar-empty" />;
                    const ymd = dateToYmd(cell);
                    const item = calendarMap.get(ymd);
                    const title = item
                      ? `${formatYmd(ymd)} ${STATUS_LABEL[item.status] || item.status}\n缺失任务: ${(item.missing_required_tasks || []).join(", ") || "-"}`
                      : `${formatYmd(ymd)} 无数据`;
                    return (
                      <div key={`${panel.monthLabel}-${ymd}`} className={`calendar-cell ${statusClass(item?.status)}`} title={title}>
                        <span className="sync-day">{cell.getDate()}</span>
                      </div>
                    );
                  })}
                </div>
                <div className="sync-missing-list">
                  {panel.items.map((item) => (
                    <span key={item.trade_date} className="badge sync-missing-item" title={`缺失任务: ${(item.missing_required_tasks || []).join(", ")}`}>
                      {formatYmd(item.trade_date)}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      <section className="panel">
        <h2>执行同步任务</h2>
        <form className="filters" onSubmit={createJob}>
          <label className="field">
            <span>开始日期</span>
            <input type="date" value={jobStartDate} onChange={(e) => setJobStartDate(e.target.value)} />
          </label>
          <label className="field">
            <span>结束日期</span>
            <input type="date" value={jobEndDate} onChange={(e) => setJobEndDate(e.target.value)} />
          </label>
          <div className="sync-job-actions">
            <button className="primary sync-job-btn" type="submit" disabled={job?.status === "running" || job?.status === "pending"}>
              {job?.status === "running" || job?.status === "pending" ? "执行中..." : "执行 daily.sh"}
            </button>
            <button
              className="primary sync-job-btn sync-job-btn--stop"
              type="button"
              onClick={stopJob}
              disabled={!jobId || !["running", "pending"].includes(String(job?.status || ""))}
            >
              停止任务
            </button>
          </div>
        </form>
        {jobError ? <div className="error">{jobError}</div> : null}
        {job ? (
          <div className="sync-job-meta">
            <span className="badge">Job: {job.job_id}</span>
            <span className={`badge ${statusClass(job.status)}`}>{STATUS_LABEL[job.status] || job.status}</span>
            <span className="badge">
              范围: {formatYmd(job.start_date)} ~ {formatYmd(job.end_date)}
            </span>
            {job.exit_code !== null && job.exit_code !== undefined ? (
              <span className="badge">exit_code: {job.exit_code}</span>
            ) : null}
          </div>
        ) : null}
        <pre className="sync-log-box">{logs || "暂无日志输出"}</pre>
      </section>
    </main>
  );
}

