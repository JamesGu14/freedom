import Link from "next/link";

const STOCK_MODULES = [
  { title: "财务与分红", desc: "利润表、资产负债表、现金流量表、财务指标、分红送股。" },
  { title: "股东与筹码", desc: "股东人数、前十大股东、前十大流通股东、筹码绩效与筹码分布。" },
  { title: "两融与资金流", desc: "融资融券明细、个股资金流、港股通持股、CCASS 持股。" },
  { title: "停复牌与事件", desc: "停复牌与机构调研，后续可继续扩到回购和股东变动。" },
];

const MARKET_MODULES = [
  { title: "指数研究", desc: "指数基础字典、核心指数日线、大盘指数每日指标、指数扩展因子。" },
  { title: "行业研究", desc: "申万 / 中信行业日线、行业成分与行业强弱快照。" },
  { title: "市场资金", desc: "沪深港通整体资金流向。" },
];

export default function ResearchHomePage() {
  return (
    <main className="page">
      <header className="header">
        <div>
          <p className="eyebrow">Research</p>
          <h1>研究数据中心</h1>
          <p className="subtitle">把已接入但分散的数据聚合成可浏览、可筛选、可供 OpenClaw 使用的研究视图。</p>
        </div>
      </header>

      <section className="research-home-grid">
        <article className="panel research-home-card">
          <div className="panel-title-row">
            <h2>个股研究</h2>
            <Link className="primary" href="/research/stocks/000001.SZ">
              打开示例
            </Link>
          </div>
          <p className="subtitle">围绕单只股票查看财务、分红、股东、筹码、资金流、停复牌和事件。</p>
          <div className="research-module-list">
            {STOCK_MODULES.map((item) => (
              <div key={item.title} className="research-module-card">
                <strong>{item.title}</strong>
                <p>{item.desc}</p>
              </div>
            ))}
          </div>
        </article>

        <article className="panel research-home-card">
          <div className="panel-title-row">
            <h2>市场研究</h2>
            <Link className="primary" href="/research/market">
              打开页面
            </Link>
          </div>
          <p className="subtitle">围绕指数、行业和市场资金做横向研究。</p>
          <div className="research-module-list">
            {MARKET_MODULES.map((item) => (
              <div key={item.title} className="research-module-card">
                <strong>{item.title}</strong>
                <p>{item.desc}</p>
              </div>
            ))}
          </div>
        </article>
      </section>

      <section className="panel">
        <h2>OpenClaw API</h2>
        <p className="subtitle">后端已经新增 research 聚合接口，建议 OpenClaw 优先调用这些接口，而不是自己拼多个 raw API。</p>
        <div className="research-api-list">
          <code>/api/research/stocks/{`{ts_code}`}/overview</code>
          <code>/api/research/stocks/{`{ts_code}`}/financials</code>
          <code>/api/research/stocks/{`{ts_code}`}/dividends</code>
          <code>/api/research/stocks/{`{ts_code}`}/holders</code>
          <code>/api/research/stocks/{`{ts_code}`}/chips</code>
          <code>/api/research/stocks/{`{ts_code}`}/flows</code>
          <code>/api/research/stocks/{`{ts_code}`}/events</code>
          <code>/api/research/market/indexes</code>
          <code>/api/research/market/indexes/{`{ts_code}`}</code>
          <code>/api/research/market/sectors</code>
          <code>/api/research/market/hsgt-flow</code>
        </div>
      </section>
    </main>
  );
}
