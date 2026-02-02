import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/router";
import Link from "next/link";
import { apiFetch } from "../../lib/api";

const formatDate = (value) => {
  if (!value || value.length !== 8) {
    return value || "-";
  }
  return `${value.slice(0, 4)}-${value.slice(4, 6)}-${value.slice(6, 8)}`;
};

export default function SectorDetail() {
  const router = useRouter();
  const { index_code: indexCode, version: versionQuery } = router.query;
  const [version, setVersion] = useState("2021");
  const [industry, setIndustry] = useState(null);
  const [members, setMembers] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(200);
  const [showHistory, setShowHistory] = useState(false);
  const [breadcrumbs, setBreadcrumbs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (typeof versionQuery === "string" && versionQuery) {
      setVersion(versionQuery);
    }
  }, [versionQuery]);

  const params = useMemo(() => {
    const search = new URLSearchParams();
    search.set("version", version);
    search.set("is_new", showHistory ? "ALL" : "Y");
    search.set("page", String(page));
    search.set("page_size", String(pageSize));
    return search.toString();
  }, [version, showHistory, page, pageSize]);

  const loadSector = async () => {
    if (!indexCode) {
      return;
    }
    setLoading(true);
    setError("");
    try {
      const res = await apiFetch(`/sectors/${indexCode}?${params}`);
      if (!res.ok) {
        throw new Error(`加载失败: ${res.status}`);
      }
      const data = await res.json();
      setIndustry(data.industry || null);
      setMembers(data.members || []);
      setTotal(data.total || 0);
      setBreadcrumbs(data.breadcrumbs || []);
    } catch (err) {
      setError(err.message || "加载失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSector();
  }, [indexCode, params]);

  useEffect(() => {
    setPage(1);
  }, [showHistory, version, indexCode]);

  const totalPages = Math.max(Math.ceil(total / pageSize), 1);
  const returnUrl = encodeURIComponent(router.asPath || `/sectors/${indexCode}`);

  return (
    <main className="page">
      <header className="header">
        <div>
          <p className="eyebrow">Quant Platform</p>
          <h1>{industry?.industry_name || "板块详情"}</h1>
          <p className="subtitle">
            {industry?.index_code || indexCode} · {version}版
          </p>
        </div>
        <Link className="primary" href="/sectors">
          返回板块
        </Link>
      </header>

      {breadcrumbs.length > 0 ? (
        <nav className="breadcrumbs">
          {breadcrumbs.map((crumb, idx) => (
            <span key={`${crumb.index_code}-${idx}`} className="breadcrumb-item">
              <Link href={`/sectors/${crumb.index_code}?version=${version}`}>
                {crumb.name || crumb.index_code}
              </Link>
              {idx < breadcrumbs.length - 1 ? <span className="breadcrumb-sep">/</span> : null}
            </span>
          ))}
        </nav>
      ) : null}

      {error ? <div className="error">{error}</div> : null}

      <section className="panel sector-detail">
        <div className="sector-info">
          <div>
            <h3>行业信息</h3>
            <p className="sector-info-text">
              代码：{industry?.index_code || "-"} · 版本：{industry?.version || version}
            </p>
            <p className="sector-info-text">
              层级：{industry?.level_name || "-"} · 成分股数：
              {industry?.constituent_count ?? "-"}
            </p>
          </div>
          <label className="toggle">
            <input
              type="checkbox"
              checked={showHistory}
              onChange={(event) => setShowHistory(event.target.checked)}
            />
            <span className="toggle-label">显示历史成分股</span>
          </label>
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
            <small>尝试切换显示历史成分股</small>
          </div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>股票代码</th>
                <th>股票名称</th>
                <th>纳入日期</th>
                <th>剔除日期</th>
                <th>状态</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {members.map((item) => (
                <tr key={`${item.ts_code}-${item.l3_code}-${item.in_date}`}>
                  <td className="code-cell">{item.ts_code}</td>
                  <td className="name-cell">{item.name || "-"}</td>
                  <td>{formatDate(item.in_date)}</td>
                  <td>{formatDate(item.out_date)}</td>
                  <td>
                    <span className={`status-pill ${item.is_new === "Y" ? "status-active" : "status-disabled"}`}>
                      {item.is_new === "Y" ? "当前" : "历史"}
                    </span>
                  </td>
                  <td>
                    <Link
                      className="link-button"
                      href={`/stocks/${item.ts_code}?returnUrl=${returnUrl}`}
                    >
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
