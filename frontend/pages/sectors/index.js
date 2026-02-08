import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { apiFetch } from "../../lib/api";

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

const getThreeDayChanges = (row) => {
  const items = [
    { value: row.pct_chg_1, date: row.pct_chg_1_date },
    { value: row.pct_chg_2, date: row.pct_chg_2_date },
    { value: row.pct_chg_3, date: row.pct_chg_3_date },
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

export default function Sectors() {
  const [versions, setVersions] = useState(["2021", "2014"]);
  const [version, setVersion] = useState("2021");

  const [l1List, setL1List] = useState([]);
  const [l2List, setL2List] = useState([]);
  const [l3List, setL3List] = useState([]);

  const [selectedL1, setSelectedL1] = useState(null);
  const [selectedL2, setSelectedL2] = useState(null);
  const [selectedL3, setSelectedL3] = useState(null);

  const [members, setMembers] = useState([]);
  const [membersTotal, setMembersTotal] = useState(0);
  const [membersPage, setMembersPage] = useState(1);
  const [membersPageSize] = useState(100);
  const [membersLoading, setMembersLoading] = useState(false);
  const [sortPct3d, setSortPct3d] = useState(null);

  const [treeLoading, setTreeLoading] = useState(false);
  const [error, setError] = useState("");

  const loadVersions = useCallback(async () => {
    try {
      const res = await apiFetch("/sectors/versions");
      if (!res.ok) return;
      const data = await res.json();
      if (Array.isArray(data.items) && data.items.length > 0) {
        setVersions(data.items);
        if (!data.items.includes(version)) setVersion(data.items[0]);
      }
    } catch (err) {
      // ignore
    }
  }, []);

  const loadL1 = useCallback(async () => {
    setTreeLoading(true);
    setError("");
    try {
      const params = new URLSearchParams();
      params.set("version", version);
      params.set("level", "1");
      const res = await apiFetch(`/sectors?${params.toString()}`);
      if (!res.ok) throw new Error(`加载失败: ${res.status}`);
      const data = await res.json();
      setL1List(data.items || []);
      setL2List([]);
      setL3List([]);
      setSelectedL1(null);
      setSelectedL2(null);
      setSelectedL3(null);
    } catch (err) {
      setError(err.message || "加载失败");
    } finally {
      setTreeLoading(false);
    }
  }, [version]);

  const loadL2 = useCallback(async (level1Code) => {
    if (!level1Code) {
      setL2List([]);
      setL3List([]);
      setSelectedL2(null);
      setSelectedL3(null);
      return;
    }
    setTreeLoading(true);
    setError("");
    try {
      const params = new URLSearchParams();
      params.set("version", version);
      params.set("level", "2");
      params.set("level1_code", level1Code);
      const res = await apiFetch(`/sectors?${params.toString()}`);
      if (!res.ok) throw new Error(`加载失败: ${res.status}`);
      const data = await res.json();
      setL2List(data.items || []);
      setL3List([]);
      setSelectedL2(null);
      setSelectedL3(null);
    } catch (err) {
      setError(err.message || "加载失败");
    } finally {
      setTreeLoading(false);
    }
  }, [version]);

  const loadL3 = useCallback(async (parentCode) => {
    if (!parentCode) {
      setL3List([]);
      setSelectedL3(null);
      return;
    }
    setTreeLoading(true);
    setError("");
    try {
      const params = new URLSearchParams();
      params.set("version", version);
      params.set("level", "3");
      params.set("parent_code", parentCode);
      const res = await apiFetch(`/sectors?${params.toString()}`);
      if (!res.ok) throw new Error(`加载失败: ${res.status}`);
      const data = await res.json();
      setL3List(data.items || []);
      setSelectedL3(null);
    } catch (err) {
      setError(err.message || "加载失败");
    } finally {
      setTreeLoading(false);
    }
  }, [version]);

  const loadMembers = useCallback(
    async (page = 1) => {
      const params = new URLSearchParams();
      params.set("version", version);
      params.set("is_new", "Y");
      params.set("page", String(page));
      params.set("page_size", String(membersPageSize));

      if (selectedL3?.index_code) {
        params.set("l3_code", selectedL3.index_code);
      } else if (selectedL2?.index_code) {
        params.set("l2_code", selectedL2.index_code);
      } else if (selectedL1?.index_code) {
        params.set("l1_code", selectedL1.index_code);
      } else {
        setMembers([]);
        setMembersTotal(0);
        return;
      }

      setMembersLoading(true);
      try {
        const res = await apiFetch(`/sectors/members?${params.toString()}`);
        if (!res.ok) throw new Error(`加载失败: ${res.status}`);
        const data = await res.json();
        setMembers(data.items || []);
        setMembersTotal(data.total ?? 0);
        setMembersPage(page);
      } catch (err) {
        setMembers([]);
        setMembersTotal(0);
      } finally {
        setMembersLoading(false);
      }
    },
    [version, selectedL1, selectedL2, selectedL3, membersPageSize]
  );

  useEffect(() => {
    loadVersions();
  }, [loadVersions]);

  useEffect(() => {
    loadL1();
  }, [loadL1]);

  useEffect(() => {
    if (selectedL1) {
      loadL2(selectedL1.industry_code);
    } else {
      setL2List([]);
      setL3List([]);
    }
  }, [selectedL1, version]);

  useEffect(() => {
    if (selectedL2) {
      loadL3(selectedL2.industry_code);
    } else {
      setL3List([]);
    }
  }, [selectedL2, version]);

  useEffect(() => {
    loadMembers(1);
  }, [selectedL1, selectedL2, selectedL3]);

  const handleSelectL1 = (item) => {
    setSelectedL1(item);
  };

  const handleSelectL2 = (item) => {
    setSelectedL2(item);
  };

  const handleSelectL3 = (item) => {
    setSelectedL3(item);
  };

  const membersTotalPages = Math.max(Math.ceil(membersTotal / membersPageSize), 1);

  const sortedMembers = [...members].sort((a, b) => {
    if (sortPct3d == null) return 0;
    const va = a.pct_chg_3d;
    const vb = b.pct_chg_3d;
    const na = Number(va);
    const nb = Number(vb);
    if (Number.isNaN(na) && Number.isNaN(nb)) return 0;
    if (Number.isNaN(na)) return sortPct3d === "desc" ? 1 : -1;
    if (Number.isNaN(nb)) return sortPct3d === "desc" ? -1 : 1;
    if (sortPct3d === "desc") return nb - na;
    return na - nb;
  });

  const handleSortPct3d = () => {
    setSortPct3d((prev) => (prev == null ? "desc" : prev === "desc" ? "asc" : "desc"));
  };

  const currentLabel =
    selectedL3
      ? selectedL3.industry_name
      : selectedL2
        ? selectedL2.industry_name
        : selectedL1
          ? selectedL1.industry_name
          : null;

  return (
    <main className="page sectors-page">
      <header className="header sectors-header">
        <div>
          <p className="eyebrow">Quant Platform</p>
          <h1>板块总览</h1>
          <p className="subtitle">申万行业树形浏览（{version}版）</p>
        </div>
        <div className="header-actions">
          <div className="field">
            <label htmlFor="versionSelect">版本</label>
            <select
              id="versionSelect"
              value={version}
              onChange={(e) => setVersion(e.target.value)}
            >
              {versions.map((v) => (
                <option key={v} value={v}>
                  {v}版
                </option>
              ))}
            </select>
          </div>
        </div>
      </header>

      {error ? <div className="error">{error}</div> : null}

      <div className="sectors-layout">
        <aside className="sectors-tree-panel">
          <div className="tree-panel-header">
            <h3>行业层级</h3>
          </div>
          <div className="tree-columns">
            <div className="tree-column">
              <div className="tree-column-title">一级行业</div>
              {treeLoading && l1List.length === 0 ? (
                <div className="tree-loading">
                  <div className="spinner"></div>
                  <span>加载中...</span>
                </div>
              ) : (
                <ul className="tree-list">
                  {l1List.map((item) => (
                    <li key={item.industry_code}>
                      <button
                        type="button"
                        className={`tree-item ${selectedL1?.industry_code === item.industry_code ? "active" : ""}`}
                        onClick={() => handleSelectL1(item)}
                      >
                        <span className="tree-item-name">{item.industry_name || "-"}</span>
                        <span className="tree-item-count">
                          {item.constituent_count ?? "-"}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className="tree-column">
              <div className="tree-column-title">二级行业</div>
              {selectedL1 && treeLoading && l2List.length === 0 ? (
                <div className="tree-loading">
                  <div className="spinner"></div>
                  <span>加载中...</span>
                </div>
              ) : (
                <ul className="tree-list">
                  {l2List.map((item) => (
                    <li key={item.industry_code}>
                      <button
                        type="button"
                        className={`tree-item ${selectedL2?.industry_code === item.industry_code ? "active" : ""}`}
                        onClick={() => handleSelectL2(item)}
                      >
                        <span className="tree-item-name">{item.industry_name || "-"}</span>
                        <span className="tree-item-count">
                          {item.constituent_count ?? "-"}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className="tree-column">
              <div className="tree-column-title">三级行业</div>
              {selectedL2 && treeLoading && l3List.length === 0 ? (
                <div className="tree-loading">
                  <div className="spinner"></div>
                  <span>加载中...</span>
                </div>
              ) : (
                <ul className="tree-list">
                  {l3List.map((item) => (
                    <li key={item.industry_code}>
                      <button
                        type="button"
                        className={`tree-item ${selectedL3?.industry_code === item.industry_code ? "active" : ""}`}
                        onClick={() => handleSelectL3(item)}
                      >
                        <span className="tree-item-name">{item.industry_name || "-"}</span>
                        <span className="tree-item-count">
                          {item.constituent_count ?? "-"}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </aside>

        <section className="sectors-stock-panel">
          <div className="stock-panel-header">
            <h3>
              {currentLabel ? `成分股 · ${currentLabel}` : "成分股"}
            </h3>
          </div>
          {!currentLabel ? (
            <div className="stock-panel-empty">
              <span className="empty-icon">📋</span>
              <p>请在左侧选择一级 / 二级 / 三级行业</p>
            </div>
          ) : membersLoading && members.length === 0 ? (
            <div className="loading-container">
              <div className="spinner"></div>
              <p>加载中...</p>
            </div>
          ) : (
            <>
              <div className="table-wrap stock-table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>股票代码</th>
                      <th>股票名称</th>
                      <th className="th-numeric">近三日分别涨跌</th>
                      <th
                        className="th-sortable th-numeric"
                        onClick={handleSortPct3d}
                        onKeyDown={(e) => e.key === "Enter" && handleSortPct3d()}
                        role="button"
                        tabIndex={0}
                        title={sortPct3d == null ? "点击按近三日涨跌排序" : sortPct3d === "desc" ? "点击改为升序" : "点击改为降序"}
                      >
                        近三日涨跌
                        {sortPct3d != null && (
                          <span className="sort-indicator" aria-hidden>
                            {sortPct3d === "desc" ? " ↓" : " ↑"}
                          </span>
                        )}
                      </th>
                      <th>纳入日期</th>
                      <th>操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sortedMembers.length === 0 ? (
                      <tr>
                        <td colSpan="6" className="empty">
                          <div className="empty-state">
                            <span className="empty-icon">📉</span>
                            <p>暂无成分股</p>
                          </div>
                        </td>
                      </tr>
                    ) : (
                      sortedMembers.map((row) => (
                        <tr key={`${row.ts_code}-${row.l3_code}-${row.in_date}`}>
                          <td className="code-cell">{row.ts_code}</td>
                          <td className="name-cell">{row.name || "-"}</td>
                          <td className="pct-three-days">
                            {getThreeDayChanges(row).map((item, index) => (
                              <span
                                key={`${row.ts_code}-pct-${index}`}
                                className={`change-pill change-pill-sm ${getChangeClass(item.value)}`}
                                title={item.date ? `交易日 ${formatDate(item.date)}` : "交易日未知"}
                              >
                                {formatPct(item.value)}
                              </span>
                            ))}
                          </td>
                          <td>
                            <span
                              className={`change-pill ${getChangeClass(row.pct_chg_3d)}`}
                              title="近 3 个交易日涨跌幅合计"
                            >
                              {formatPct(row.pct_chg_3d)}
                            </span>
                          </td>
                          <td>{formatDate(row.in_date)}</td>
                          <td>
                            <Link
                              className="link-button"
                              href={`/stocks/${row.ts_code}?returnUrl=${encodeURIComponent("/sectors")}`}
                            >
                              查看K线
                            </Link>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
              <div className="pagination">
                <span>
                  共 {membersTotal} 条，第 {membersPage} / {membersTotalPages} 页
                </span>
                <div className="pager-actions">
                  <button
                    type="button"
                    onClick={() => loadMembers(Math.max(membersPage - 1, 1))}
                    disabled={membersLoading || membersPage <= 1}
                  >
                    上一页
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      loadMembers(Math.min(membersPage + 1, membersTotalPages))
                    }
                    disabled={membersLoading || membersPage >= membersTotalPages}
                  >
                    下一页
                  </button>
                </div>
              </div>
            </>
          )}
        </section>
      </div>
    </main>
  );
}
