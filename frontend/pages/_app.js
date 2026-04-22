import "../styles/globals.css";
import Head from "next/head";
import Link from "next/link";
import { useRouter } from "next/router";
import { useEffect, useState, useCallback } from "react";
import { AuthProvider, useAuth } from "../lib/auth";
import { getToken } from "../lib/api";

/* ── Inline SVG icon wrapper (Feather-style, 18×18) ── */
function Ico({ children }) {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {children}
    </svg>
  );
}

/* ── Navigation configuration ── */
const NAV = [
  {
    href: "/",
    label: "首页",
    exact: true,
    icon: (
      <Ico>
        <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
      </Ico>
    ),
  },
  {
    href: "/sector-ranking",
    label: "板块排名",
    icon: (
      <Ico>
        <line x1="18" y1="20" x2="18" y2="10" />
        <line x1="12" y1="20" x2="12" y2="4" />
        <line x1="6" y1="20" x2="6" y2="14" />
      </Ico>
    ),
  },
  {
    href: "/market-index",
    label: "大盘指数",
    icon: (
      <Ico>
        <polyline points="23 6 13.5 15.5 8.5 10.5 1 18" />
        <polyline points="17 6 23 6 23 12" />
      </Ico>
    ),
  },
  {
    href: "/stock-list",
    label: "股票列表",
    icon: (
      <Ico>
        <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
        <polyline points="9 22 9 12 15 12 15 22" />
      </Ico>
    ),
  },
  {
    href: "/sectors",
    label: "板块",
    icon: (
      <Ico>
        <rect x="3" y="3" width="7" height="7" />
        <rect x="14" y="3" width="7" height="7" />
        <rect x="14" y="14" width="7" height="7" />
        <rect x="3" y="14" width="7" height="7" />
      </Ico>
    ),
  },
  {
    href: "/daily-signals",
    label: "Daily Signals",
    adminOnly: true,
    icon: (
      <Ico>
        <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
      </Ico>
    ),
  },
  {
    href: "/daily-signals-legacy",
    label: "Daily Signals(旧)",
    adminOnly: true,
    icon: (
      <Ico>
        <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
      </Ico>
    ),
  },
  {
    href: "/agent-freedom",
    label: "财神爷",
    adminOnly: true,
    icon: (
      <Ico>
        <rect x="3" y="4" width="18" height="16" rx="2" />
        <line x1="3" y1="10" x2="21" y2="10" />
        <circle cx="16" cy="15" r="1.5" />
      </Ico>
    ),
  },
  {
    href: "/research",
    label: "研究中心",
    icon: (
      <Ico>
        <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
        <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
      </Ico>
    ),
  },
  {
    href: "/watchlist",
    label: "自选",
    icon: (
      <Ico>
        <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
      </Ico>
    ),
  },
  "---",
  {
    href: "/strategies",
    label: "策略",
    adminOnly: true,
    icon: (
      <Ico>
        <polyline points="16 18 22 12 16 6" />
        <polyline points="8 6 2 12 8 18" />
      </Ico>
    ),
  },
  {
    href: "/backtests",
    label: "回测",
    adminOnly: true,
    icon: (
      <Ico>
        <circle cx="12" cy="12" r="10" />
        <polygon points="10 8 16 12 10 16 10 8" />
      </Ico>
    ),
  },
];

/* ── App Shell with sidebar ── */
function AppShell({ Component, pageProps }) {
  const router = useRouter();
  const { token, username, roles, initialized, logout } = useAuth();
  const isAdmin = Array.isArray(roles) && roles.some((role) => String(role).trim().toLowerCase() === "admin");

  const [collapsed, setCollapsed] = useState(false);
  const [drawer, setDrawer] = useState(false);

  /* Restore sidebar state from localStorage */
  useEffect(() => {
    try {
      if (localStorage.getItem("fq_sidebar") === "1") setCollapsed(true);
    } catch {}
  }, []);

  const toggleSidebar = useCallback(() => {
    setCollapsed((prev) => {
      const next = !prev;
      try {
        localStorage.setItem("fq_sidebar", next ? "1" : "0");
      } catch {}
      return next;
    });
  }, []);

  /* Close mobile drawer on navigation */
  useEffect(() => {
    setDrawer(false);
  }, [router.pathname]);

  useEffect(() => {
    if (!initialized) return;
    const currentToken = getToken();
    if (!currentToken) {
      window.location.href = "/management";
    }
  }, [initialized]);

  const isActive = (href, exact) =>
    exact
      ? router.pathname === href
      : router.pathname === href || router.pathname.startsWith(href + "/");

  return (
    <>
      <Head>
        <title>Freedom Quant</title>
        <link rel="icon" href="/freedom/favicon.ico" />
      </Head>

      {/* Mobile backdrop */}
      {drawer && (
        <div className="sidebar-overlay" onClick={() => setDrawer(false)} />
      )}

      <div
        className={`app-layout${collapsed ? " app-layout--collapsed" : ""}`}
      >
        {/* ── Sidebar ── */}
        <aside className={`sidebar${drawer ? " sidebar--open" : ""}`}>
          <div className="sidebar__brand">
            <span className="sidebar__logo">F</span>
            <span className="sidebar__brand-text">Freedom</span>
          </div>

          <nav className="sidebar__nav">
            {NAV.map((item, i) =>
              item === "---" ? (
                <div key={`d${i}`} className="sidebar__divider" />
              ) : item.adminOnly && !isAdmin ? (
                <span
                  key={item.href}
                  className="sidebar__item sidebar__item--disabled"
                  title={collapsed ? item.label : undefined}
                >
                  <span className="sidebar__icon">{item.icon}</span>
                  <span className="sidebar__label">{item.label}</span>
                </span>
              ) : (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`sidebar__item${isActive(item.href, item.exact) ? " sidebar__item--active" : ""}`}
                  title={collapsed ? item.label : undefined}
                >
                  <span className="sidebar__icon">{item.icon}</span>
                  <span className="sidebar__label">{item.label}</span>
                </Link>
              )
            )}

            {isAdmin && (
              <>
                <div className="sidebar__divider" />
                <Link
                  href="/data-sync"
                  className={`sidebar__item${isActive("/data-sync") ? " sidebar__item--active" : ""}`}
                  title={collapsed ? "数据同步" : undefined}
                >
                  <span className="sidebar__icon">
                    <Ico>
                      <path d="M21 12a9 9 0 1 1-3.2-6.9" />
                      <polyline points="21 3 21 9 15 9" />
                      <path d="M3 12a9 9 0 0 0 15.5 6.4" />
                    </Ico>
                  </span>
                   <span className="sidebar__label">数据同步</span>
                </Link>
              </>
            )}
          </nav>

          <div className="sidebar__footer">
            <button
              type="button"
              className="sidebar__item sidebar__collapse-btn"
              onClick={toggleSidebar}
              title={collapsed ? "展开侧栏" : "收起侧栏"}
            >
              <span className="sidebar__icon">
                <Ico>
                  <polyline points="11 17 6 12 11 7" />
                  <polyline points="18 17 13 12 18 7" />
                </Ico>
              </span>
              <span className="sidebar__label">收起</span>
            </button>
            {token && (
              <button
                type="button"
                className="sidebar__item"
                onClick={logout}
                title={collapsed ? "退出" : undefined}
              >
                <span className="sidebar__icon">
                  <Ico>
                    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
                    <polyline points="16 17 21 12 16 7" />
                    <line x1="21" y1="12" x2="9" y2="12" />
                  </Ico>
                </span>
                <span className="sidebar__label">{username || "退出"}</span>
              </button>
            )}
          </div>
        </aside>

        {/* Mobile hamburger */}
        <button
          type="button"
          className="mobile-menu-btn"
          onClick={() => setDrawer(true)}
          aria-label="菜单"
        >
          <Ico>
            <line x1="3" y1="12" x2="21" y2="12" />
            <line x1="3" y1="6" x2="21" y2="6" />
            <line x1="3" y1="18" x2="21" y2="18" />
          </Ico>
        </button>

        {/* ── Main content ── */}
        <div className="app-main">
          <Component {...pageProps} />
        </div>
      </div>
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
