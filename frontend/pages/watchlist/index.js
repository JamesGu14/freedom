import { useEffect, useState } from "react";
import Link from "next/link";
import { apiFetch } from "../../lib/api";

const formatDateTime = (value) => {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(
    date.getDate()
  ).padStart(2, "0")} ${String(date.getHours()).padStart(2, "0")}:${String(
    date.getMinutes()
  ).padStart(2, "0")}`;
};

export default function WatchlistGroups() {
  const [groups, setGroups] = useState([]);
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const loadGroups = async () => {
    setLoading(true);
    try {
      const res = await apiFetch(`/stock-groups`);
      if (!res.ok) {
        throw new Error(`加载失败: ${res.status}`);
      }
      const data = await res.json();
      setGroups(data.items || []);
    } catch (err) {
      setError(err.message || "加载失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadGroups();
  }, []);

  const handleCreate = async (event) => {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) {
      setError("请输入分组名称");
      return;
    }
    setError("");
    setSaving(true);
    try {
      const res = await apiFetch(`/stock-groups`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: trimmed }),
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        throw new Error(detail.detail || `创建失败: ${res.status}`);
      }
      setName("");
      await loadGroups();
    } catch (err) {
      setError(err.message || "创建失败");
    } finally {
      setSaving(false);
    }
  };

  return (
    <main className="page">
      <header className="header">
        <div>
          <p className="eyebrow">Watchlist</p>
          <h1>自选分组</h1>
          <p className="subtitle">按主题整理你关注的股票组合</p>
        </div>
        <div className="header-panel">
          <form className="group-create" onSubmit={handleCreate}>
            <div className="field">
              <label htmlFor="groupName">分组名称</label>
              <input
                id="groupName"
                type="text"
                placeholder="例如 大盘核心"
                value={name}
                onChange={(event) => setName(event.target.value)}
              />
            </div>
            <button className="primary" type="submit" disabled={saving}>
              {saving ? "创建中..." : "创建分组"}
            </button>
          </form>
        </div>
      </header>

      {error ? <div className="error">{error}</div> : null}

      <section className="group-grid">
        {loading ? (
          <div className="loading-container">
            <div className="spinner"></div>
            <p>加载中...</p>
          </div>
        ) : groups.length === 0 ? (
          <div className="empty-card">
            <span className="empty-icon">🧩</span>
            <p>还没有自选分组</p>
            <small>创建一个分组开始维护你的关注池</small>
          </div>
        ) : (
          groups.map((group) => (
            <Link key={group.id} href={`/watchlist/${group.id}`} className="group-card">
              <div className="group-card-header">
                <h3>{group.name || "未命名"}</h3>
                <span className="group-count">{group.count || 0} 支</span>
              </div>
              <p className="group-meta">创建时间：{formatDateTime(group.created_at)}</p>
              <div className="group-link">进入分组 →</div>
            </Link>
          ))
        )}
      </section>
    </main>
  );
}
