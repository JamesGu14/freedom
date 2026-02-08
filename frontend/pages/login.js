import { useState } from "react";
import { useRouter } from "next/router";
import { useAuth } from "../lib/auth";

export default function LoginPage() {
  const router = useRouter();
  const { login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (event) => {
    event.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login(username.trim(), password);
      router.replace("/");
    } catch (err) {
      setError(err.message || "登录失败");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="page auth-page">
      <section className="auth-card">
        <div className="auth-header">
          <p className="eyebrow">Freedom Quant</p>
          <h1>登录</h1>
          <p className="subtitle">使用管理员账号进入系统</p>
        </div>
        <form className="auth-form" onSubmit={handleSubmit}>
          <label className="field">
            <span>用户名</span>
            <input
              type="text"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              placeholder="请输入用户名"
            />
          </label>
          <label className="field">
            <span>密码</span>
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="请输入密码"
            />
          </label>
          {error ? <div className="error">{error}</div> : null}
          <button className="primary" type="submit" disabled={loading}>
            {loading ? "登录中..." : "登录"}
          </button>
        </form>
      </section>
    </main>
  );
}
