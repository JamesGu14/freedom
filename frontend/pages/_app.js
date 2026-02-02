import "../styles/globals.css";
import Link from "next/link";
import { useRouter } from "next/router";
import { useEffect } from "react";
import { AuthProvider, useAuth } from "../lib/auth";

function AppShell({ Component, pageProps }) {
  const router = useRouter();
  const { token, initialized, logout } = useAuth();

  useEffect(() => {
    if (!initialized) return;
    const isLoginPage = router.pathname === "/login";
    if (!token && !isLoginPage) {
      router.replace("/login");
      return;
    }
    if (token && isLoginPage) {
      router.replace("/");
    }
  }, [token, initialized, router.pathname]);

  return (
    <>
      <nav className="top-nav">
        <div className="nav-inner">
          <div className="brand">
            <span className="brand-mark">◎</span>
            <span>Freedom Quant</span>
          </div>
          <div className="nav-links">
            <Link href="/" className="nav-link">
              首页
            </Link>
            <Link href="/sectors" className="nav-link">
              板块
            </Link>
            <Link href="/daily-signals" className="nav-link">
              Daily Signals
            </Link>
            <Link href="/watchlist" className="nav-link">
              自选
            </Link>
            <Link href="/users" className="nav-link">
              用户管理
            </Link>
          </div>
          <div className="nav-actions">
            {token ? (
              <button className="nav-link nav-button" onClick={logout}>
                退出
              </button>
            ) : (
              <Link href="/login" className="nav-link">
                登录
              </Link>
            )}
          </div>
        </div>
      </nav>
      <Component {...pageProps} />
    </>
  );
}

export default function App({ Component, pageProps }) {
  return (
    <AuthProvider>
      <AppShell Component={Component} pageProps={pageProps} />
    </AuthProvider>
  );
}
