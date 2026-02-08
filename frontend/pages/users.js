import { useEffect, useState } from "react";
import { apiFetch } from "../lib/api";

const emptyForm = { username: "", password: "", display_name: "" };

export default function UsersPage() {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(10);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [form, setForm] = useState(emptyForm);

  const loadUsers = async (overridePage) => {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams();
      params.set("page", String(overridePage || page));
      params.set("page_size", String(pageSize));
      if (search.trim()) params.set("search", search.trim());
      if (status) params.set("status", status);
      const res = await apiFetch(`/users?${params.toString()}`);
      if (!res.ok) {
        throw new Error(`加载失败: ${res.status}`);
      }
      const data = await res.json();
      setItems(data.items || []);
      setTotal(data.total || 0);
    } catch (err) {
      setError(err.message || "加载失败");
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = (event) => {
    event.preventDefault();
    setPage(1);
    loadUsers(1);
  };

  const handleCreate = async (event) => {
    event.preventDefault();
    setError("");
    try {
      const res = await apiFetch("/users", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: form.username.trim(),
          password: form.password,
          display_name: form.display_name.trim() || undefined,
        }),
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        throw new Error(detail.detail || `创建失败: ${res.status}`);
      }
      setForm(emptyForm);
      loadUsers();
    } catch (err) {
      setError(err.message || "创建失败");
    }
  };

  const updateStatus = async (userId, nextStatus) => {
    setError("");
    const res = await apiFetch(`/users/${userId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: nextStatus }),
    });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}));
      setError(detail.detail || `更新失败: ${res.status}`);
      return;
    }
    loadUsers();
  };

  const resetPassword = async (userId) => {
    const password = window.prompt("请输入新密码");
    if (!password) return;
    const res = await apiFetch(`/users/${userId}/reset-password`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password }),
    });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}));
      setError(detail.detail || `重置失败: ${res.status}`);
      return;
    }
    setError("");
  };

  useEffect(() => {
    loadUsers();
  }, [page]);

  const totalPages = Math.max(Math.ceil(total / pageSize), 1);

  return (
    <main className="page">
      <header className="header">
        <div>
          <p className="eyebrow">Admin</p>
          <h1>用户管理</h1>
          <p className="subtitle">创建账号、启用/禁用、重置密码</p>
        </div>
      </header>

      <form className="filters" onSubmit={handleSearch}>
        <div className="field">
          <label htmlFor="searchUser">搜索</label>
          <input
            id="searchUser"
            type="text"
            placeholder="用户名"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="statusSelect">状态</label>
          <select
            id="statusSelect"
            value={status}
            onChange={(event) => setStatus(event.target.value)}
          >
            <option value="">全部</option>
            <option value="active">启用</option>
            <option value="disabled">禁用</option>
          </select>
        </div>
        <button className="primary" type="submit" disabled={loading}>
          {loading ? "查询中..." : "查询"}
        </button>
      </form>

      {error ? <div className="error">{error}</div> : null}

      <section className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>用户名</th>
              <th>显示名</th>
              <th>状态</th>
              <th>创建时间</th>
              <th>最后登录</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody className={loading ? "loading" : ""}>
            {items.length === 0 ? (
              <tr>
                <td colSpan="6" className="empty">
                  暂无数据
                </td>
              </tr>
            ) : (
              items.map((user) => (
                <tr key={user.id}>
                  <td>{user.username}</td>
                  <td>{user.display_name || "-"}</td>
                  <td>
                    <span className={`status-pill status-${user.status}`}>
                      {user.status === "active" ? "启用" : "禁用"}
                    </span>
                  </td>
                  <td>{user.created_at ? String(user.created_at).slice(0, 19) : "-"}</td>
                  <td>{user.last_login_at ? String(user.last_login_at).slice(0, 19) : "-"}</td>
                  <td className="actions">
                    {user.status === "active" ? (
                      <button
                        className="ghost"
                        onClick={() => updateStatus(user.id, "disabled")}
                      >
                        禁用
                      </button>
                    ) : (
                      <button
                        className="ghost"
                        onClick={() => updateStatus(user.id, "active")}
                      >
                        启用
                      </button>
                    )}
                    <button
                      className="ghost"
                      onClick={() => resetPassword(user.id)}
                    >
                      重置密码
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </section>

      <div className="pagination">
        <button
          className="ghost"
          onClick={() => setPage((prev) => Math.max(prev - 1, 1))}
          disabled={page <= 1}
        >
          上一页
        </button>
        <span>
          {page} / {totalPages}
        </span>
        <button
          className="ghost"
          onClick={() => setPage((prev) => Math.min(prev + 1, totalPages))}
          disabled={page >= totalPages}
        >
          下一页
        </button>
      </div>

      <section className="panel form-panel">
        <h2>新增用户</h2>
        <form className="form-grid" onSubmit={handleCreate}>
          <label className="field">
            <span>用户名</span>
            <input
              type="text"
              value={form.username}
              onChange={(event) =>
                setForm((prev) => ({ ...prev, username: event.target.value }))
              }
              required
            />
          </label>
          <label className="field">
            <span>显示名</span>
            <input
              type="text"
              value={form.display_name}
              onChange={(event) =>
                setForm((prev) => ({ ...prev, display_name: event.target.value }))
              }
            />
          </label>
          <label className="field">
            <span>密码</span>
            <input
              type="password"
              value={form.password}
              onChange={(event) =>
                setForm((prev) => ({ ...prev, password: event.target.value }))
              }
              required
            />
          </label>
          <div className="form-actions">
            <button className="primary" type="submit">
              创建
            </button>
          </div>
        </form>
      </section>
    </main>
  );
}
