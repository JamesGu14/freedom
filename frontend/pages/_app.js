import "../styles/globals.css";
import Link from "next/link";

export default function App({ Component, pageProps }) {
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
            <Link href="/daily-signals" className="nav-link">
              Daily Signals
            </Link>
            <Link href="/watchlist" className="nav-link">
              自选
            </Link>
          </div>
        </div>
      </nav>
      <Component {...pageProps} />
    </>
  );
}
