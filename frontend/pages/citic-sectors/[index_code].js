import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/router";
import Link from "next/link";
import { apiFetch } from "../../lib/api";

const formatDate = (value) => {
  if (!value || value.length !== 8) return value || "-";
  return `${value.slice(0, 4)}-${value.slice(4, 6)}-${value.slice(6, 8)}`;
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

const getFiveDayChanges = (row) => {
  const items = [
    { value: row.pct_chg_1, date: row.pct_chg_1_date },
    { value: row.pct_chg_2, date: row.pct_chg_2_date },
    { value: row.pct_chg_3, date: row.pct_chg_3_date },
    { value: row.pct_chg_4, date: row.pct_chg_4_date },
    { value: row.pct_chg_5, date: row.pct_chg_5_date },
  ];
  return items
    .slice()
    .sort((a, b) => {
      if (!a.date && !b.date) return 0;
      if (!a.date) return 1;
      if (!b.date) return -1;
      return String(a.date).localeCompare(String(b.date));
    });
};

const levelLabel = (level) => {
  if (level === 1) return "一级行业";
  if (level === 2) return "二级行业";
  if (level === 3) return "三级行业";
  return "-";
};

export default function CiticSectorDetail() {
  const router = useRouter();
  const { index_code: indexCode } = router.query;
  const [industry, setIndustry] = useState(null);
  const [members, setMembers] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(200);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const params = useMemo(() => {
    const search = new URLSearchParams();
    search.set("is_new", "Y");
    search.set("page", String(page));
    search.set("page_size", String(pageSize));
    return search.toString();
  }, [page, pageSize]);

  useEffect(() => {
    const load = async () => {
      if (!indexCode) return;
      setLoading(true);
      setError("");
      try {
        const res = await apiFetch(`/citic-sectors/${indexCode}?${params}`);
        if (!res.ok) throw new Error(`加载失败: ${res.status}`);
        const data = await res.json();
        setIndustry(data.industry || null);
        setMembers(data.members || []);
        setTotal(data.total || 0);
      } catch (err) {
        setError(err.message || "加载失败");
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [indexCode, params]);

  const totalPages = Math.max(Math.ceil(total / pageSize), 1);
  const returnUrl = encodeURIComponent(router.asPath || `/citic-sectors/${indexCode}`);

  return (
    <main className="page">
      <header className="header">
        <div>
          <p className="eyebrow">Quant Platform</p>
          <h1>{industry?.industry_name || "中信板块详情"}</h1>
          <p className="subtitle">{industry?.index_code || indexCode}</p>
        </div>
        <Link className="primary" href="/sector-ranking">
          返回板块排名
        </Link>
      </header>

      {error ? <div className="error">{error}</div> : null}

      <section className="panel sector-detail">
        <div className="sector-info">
          <div>
            <h3>板块信息</h3>
            <p className="sector-info-text">
              代码：{industry?.index_code || "-"} · 级别：{levelLabel(industry?.level)}
            </p>
            <p className="sector-info-text">
              成分股数：{industry?.member_count_latest ?? total}
            </p>
          </div>
        </div>
      </section>

      <section className="table-wrap">
        {loading ? (
          <div className="loading-container">
            <div className="spinner"></div>
            <p>加载中...</p>
          </div>
        ) : members.length === 0 ? (
          <div className="empty-state">
            <span className="empty-icon">📉</span>
            <p>暂无成分股</p>
          </div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>股票代码</th>
                <th>股票名称</th>
                <th className="th-numeric">近五日分别涨跌</th>
                <th className="th-numeric">近五日涨跌</th>
                <th>纳入日期</th>
                <th>剔除日期</th>
                <th>状态</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {members.map((item, idx) => (
                <tr key={`${item.ts_code}-${item.in_date}-${idx}`}>
                  <td className="code-cell">{item.ts_code}</td>
                  <td className="name-cell">{item.name || "-"}</td>
                  <td className="pct-three-days">
                    {getFiveDayChanges(item).map((entry, index) => (
                      <span
                        key={`${item.ts_code}-pct-${index}`}
                        className={`change-pill change-pill-sm ${getChangeClass(entry.value)}`}
                        title={entry.date ? `交易日 ${formatDate(entry.date)}` : "交易日未知"}
                      >
                        {formatPct(entry.value)}
                      </span>
                    ))}
                  </td>
                  <td className="th-numeric">
                    <span className={`change-pill ${getChangeClass(item.pct_chg_5d)}`}>
                      {formatPct(item.pct_chg_5d)}
                    </span>
                  </td>
                  <td>{formatDate(item.in_date)}</td>
                  <td>{formatDate(item.out_date)}</td>
                  <td>
                    <span className={`status-pill ${item.is_new === "Y" ? "status-active" : "status-disabled"}`}>
                      {item.is_new === "Y" ? "当前" : "历史"}
                    </span>
                  </td>
                  <td>
                    <Link className="link-button" href={`/stocks/${item.ts_code}?returnUrl=${returnUrl}`}>
                      查看K线
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <div className="pagination">
        <span>
          共 {total} 条，第 {page} / {totalPages} 页
        </span>
        <div className="pager-actions">
          <button
            type="button"
            onClick={() => setPage((current) => Math.max(current - 1, 1))}
            disabled={loading || page <= 1}
          >
            上一页
          </button>
          <button
            type="button"
            onClick={() => setPage((current) => Math.min(current + 1, totalPages))}
            disabled={loading || page >= totalPages}
          >
            下一页
          </button>
        </div>
      </div>
    </main>
  );
}

