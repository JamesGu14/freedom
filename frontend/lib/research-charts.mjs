const formatDate = (value) => {
  const text = String(value || "").replace(/-/g, "");
  if (text.length !== 8) return value || "-";
  return `${text.slice(0, 4)}-${text.slice(4, 6)}-${text.slice(6, 8)}`;
};

const toNum = (value) => {
  if (value === null || value === undefined || value === "") return null;
  const num = Number(value);
  return Number.isFinite(num) ? num : null;
};

const round = (value, digits = 2) => {
  if (!Number.isFinite(value)) return null;
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
};

const formatAmountUnit = (value) => {
  const num = toNum(value);
  if (num === null) return "-";
  const abs = Math.abs(num);
  if (abs >= 1e8) return `${round(num / 1e8)?.toFixed(2)}亿`;
  if (abs >= 1e4) return `${round(num / 1e4)?.toFixed(2)}万`;
  return `${round(num)?.toFixed(2)}`;
};

export const formatAxisUnit = (value) => formatAmountUnit(value);

export const formatTooltipMetric = (value, kind = "amount") => {
  const num = toNum(value);
  if (num === null) return "-";
  if (kind === "percent") return `${round(num)?.toFixed(2)}%`;
  return formatAmountUnit(num);
};

const seriesValue = (item, key) => toNum(item?.[key]);

const sameQuarterPrior = (sortedRows, endDate) => {
  const text = String(endDate || "");
  if (text.length !== 8) return null;
  const priorYear = `${Number(text.slice(0, 4)) - 1}${text.slice(4)}`;
  return sortedRows.find((row) => row.end_date === priorYear) || null;
};

const priorAnnual = (sortedRows, endDate) => {
  const text = String(endDate || "");
  if (text.length !== 8) return null;
  const priorAnnualDate = `${Number(text.slice(0, 4)) - 1}1231`;
  return sortedRows.find((row) => row.end_date === priorAnnualDate) || null;
};

const computeYoY = (current, previous) => {
  if (current === null || previous === null || previous === 0) return null;
  return round(((current - previous) / Math.abs(previous)) * 100);
};

const computeTtm = (current, previousSamePeriod, previousAnnual) => {
  if (current === null) return null;
  if (!previousAnnual) return current;
  const priorAnnualValue = toNum(previousAnnual);
  if (priorAnnualValue === null) return current;
  const priorPeriodValue = toNum(previousSamePeriod);
  if (priorPeriodValue === null) return priorAnnualValue;
  return round(current + priorAnnualValue - priorPeriodValue);
};

export const buildFinancialChartRows = (financials, viewMode) => {
  const indicators = Array.isArray(financials?.indicators) ? financials.indicators : [];
  const income = Array.isArray(financials?.income) ? financials.income : [];
  const cashflow = Array.isArray(financials?.cashflow) ? financials.cashflow : [];
  const shouldKeep = (endDate) => {
    if (!endDate) return false;
    return viewMode === "annual" ? String(endDate).endsWith("1231") : true;
  };

  const map = new Map();
  indicators.filter((item) => shouldKeep(item.end_date)).forEach((item) => {
    map.set(item.end_date, { ...(map.get(item.end_date) || {}), end_date: item.end_date, ann_date: item.ann_date, indicator: item });
  });
  income.filter((item) => shouldKeep(item.end_date)).forEach((item) => {
    map.set(item.end_date, { ...(map.get(item.end_date) || {}), end_date: item.end_date, ann_date: item.ann_date, income: item });
  });
  cashflow.filter((item) => shouldKeep(item.end_date)).forEach((item) => {
    map.set(item.end_date, { ...(map.get(item.end_date) || {}), end_date: item.end_date, ann_date: item.ann_date, cashflow: item });
  });

  const sorted = [...map.values()].sort((a, b) => String(a.end_date).localeCompare(String(b.end_date)));
  const enriched = sorted.map((row) => {
    const prevSamePeriod = sameQuarterPrior(sorted, row.end_date);
    const prevAnnualRow = priorAnnual(sorted, row.end_date);
    const revenue = seriesValue(row.income, "revenue");
    const nIncome = seriesValue(row.income, "n_income");
    const cashflowAct = seriesValue(row.cashflow, "n_cashflow_act");
    return {
      ...row,
      revenue,
      n_income: nIncome,
      n_cashflow_act: cashflowAct,
      roe: seriesValue(row.indicator, "roe"),
      roa: seriesValue(row.indicator, "roa"),
      grossprofit_margin: seriesValue(row.indicator, "grossprofit_margin"),
      debt_to_assets: seriesValue(row.indicator, "debt_to_assets"),
      revenue_yoy: computeYoY(revenue, seriesValue(prevSamePeriod?.income, "revenue")),
      n_income_yoy: computeYoY(nIncome, seriesValue(prevSamePeriod?.income, "n_income")),
      n_cashflow_act_yoy: computeYoY(cashflowAct, seriesValue(prevSamePeriod?.cashflow, "n_cashflow_act")),
      revenue_ttm: computeTtm(revenue, seriesValue(prevSamePeriod?.income, "revenue"), seriesValue(prevAnnualRow?.income, "revenue")),
      n_income_ttm: computeTtm(nIncome, seriesValue(prevSamePeriod?.income, "n_income"), seriesValue(prevAnnualRow?.income, "n_income")),
      n_cashflow_act_ttm: computeTtm(cashflowAct, seriesValue(prevSamePeriod?.cashflow, "n_cashflow_act"), seriesValue(prevAnnualRow?.cashflow, "n_cashflow_act")),
    };
  });

  return viewMode === "annual" ? enriched.slice(-8) : enriched.slice(-12);
};

export const buildFinancialSummaryStats = (rows) => {
  const latest = Array.isArray(rows) && rows.length > 0 ? rows.at(-1) : null;
  if (!latest) {
    return {
      latest_period: null,
      revenue_yoy: null,
      n_income_yoy: null,
      n_cashflow_act_yoy: null,
      revenue_ttm: null,
      n_income_ttm: null,
      n_cashflow_act_ttm: null,
    };
  }
  return {
    latest_period: latest.end_date ?? null,
    revenue_yoy: latest.revenue_yoy ?? null,
    n_income_yoy: latest.n_income_yoy ?? null,
    n_cashflow_act_yoy: latest.n_cashflow_act_yoy ?? null,
    revenue_ttm: latest.revenue_ttm ?? null,
    n_income_ttm: latest.n_income_ttm ?? null,
    n_cashflow_act_ttm: latest.n_cashflow_act_ttm ?? null,
  };
};

const getFinancialMetricConfig = (metricMode) => {
  if (metricMode === "yoy") {
    return {
      axisName: "同比增速",
      axisFormatter: (value) => `${round(value)?.toFixed(0)}%`,
      tooltipKind: "percent",
      amountSeries: [
        { name: "营收同比", key: "revenue_yoy", color: "#2563eb" },
        { name: "净利润同比", key: "n_income_yoy", color: "#14b8a6" },
        { name: "经营现金流同比", key: "n_cashflow_act_yoy", color: "#f59e0b" },
      ],
    };
  }
  if (metricMode === "ttm") {
    return {
      axisName: "金额",
      axisFormatter: formatAxisUnit,
      tooltipKind: "amount",
      amountSeries: [
        { name: "营收TTM", key: "revenue_ttm", color: "#2563eb" },
        { name: "净利润TTM", key: "n_income_ttm", color: "#14b8a6" },
        { name: "经营现金流TTM", key: "n_cashflow_act_ttm", color: "#f59e0b" },
      ],
    };
  }
  return {
    axisName: "金额",
    axisFormatter: formatAxisUnit,
    tooltipKind: "amount",
    amountSeries: [
      { name: "营收", key: "revenue", color: "#2563eb" },
      { name: "净利润", key: "n_income", color: "#14b8a6" },
      { name: "经营现金流", key: "n_cashflow_act", color: "#f59e0b" },
    ],
  };
};

export const buildFinancialChartOption = (rows, viewMode, metricMode = "raw") => {
  const labels = rows.map((row) => formatDate(row.end_date));
  const metricConfig = getFinancialMetricConfig(metricMode);
  const ratioSeries = [
    { name: "ROE", key: "roe", color: "#ef4444" },
    { name: "ROA", key: "roa", color: "#8b5cf6" },
    { name: "毛利率", key: "grossprofit_margin", color: "#22c55e" },
    { name: "资产负债率", key: "debt_to_assets", color: "#64748b" },
  ];

  return {
    backgroundColor: "transparent",
    animation: false,
    legend: {
      top: 8,
      textStyle: { color: "#475569", fontSize: 12 },
      data: [...metricConfig.amountSeries.map((item) => item.name), ...ratioSeries.map((item) => item.name)],
    },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "cross" },
      formatter: (params) => {
        if (!params?.length) return "";
        const row = rows[params[0].dataIndex];
        const lines = [`${formatDate(row?.end_date)} (${viewMode === "annual" ? "年度" : "季度"})`];
        if (row?.ann_date) lines.push(`公告日: ${formatDate(row.ann_date)}`);
        params.forEach((item, index) => {
          const kind = index < metricConfig.amountSeries.length ? metricConfig.tooltipKind : "percent";
          lines.push(`${item.marker}${item.seriesName}: ${formatTooltipMetric(item.value, kind)}`);
        });
        return lines.join("<br/>");
      },
    },
    grid: { left: 56, right: 72, top: 46, bottom: 56 },
    xAxis: {
      type: "category",
      data: labels,
      axisLine: { lineStyle: { color: "#cbd5e1" } },
      axisLabel: { color: "#64748b" },
    },
    yAxis: [
      {
        type: "value",
        name: metricConfig.axisName,
        axisLabel: { color: "#64748b", formatter: metricConfig.axisFormatter },
        splitLine: { lineStyle: { color: "rgba(148, 163, 184, 0.16)" } },
      },
      {
        type: "value",
        name: "比率",
        axisLabel: { color: "#64748b", formatter: (value) => `${round(value)?.toFixed(0)}%` },
        splitLine: { show: false },
      },
    ],
    series: [
      ...metricConfig.amountSeries.map((item) => ({
        name: item.name,
        type: metricMode === "raw" ? "bar" : "line",
        yAxisIndex: 0,
        data: rows.map((row) => row[item.key]),
        itemStyle: metricMode === "raw" ? { color: item.color } : undefined,
        lineStyle: metricMode !== "raw" ? { color: item.color, width: 2 } : undefined,
        symbol: metricMode === "raw" ? undefined : "circle",
        smooth: false,
      })),
      ...ratioSeries.map((item) => ({
        name: item.name,
        type: "line",
        yAxisIndex: 1,
        data: rows.map((row) => row[item.key]),
        smooth: false,
        symbol: "circle",
        lineStyle: { color: item.color, width: 2 },
      })),
    ],
  };
};

export const buildFlowChartRows = (flows, windowSize) => {
  const flowRows = Array.isArray(flows?.moneyflow_dc) ? flows.moneyflow_dc : [];
  const marginRows = Array.isArray(flows?.margin_detail) ? flows.margin_detail : [];
  return {
    moneyflow: [...flowRows].sort((a, b) => String(a.trade_date).localeCompare(String(b.trade_date))).slice(-windowSize),
    margin: [...marginRows].sort((a, b) => String(a.trade_date).localeCompare(String(b.trade_date))).slice(-windowSize),
  };
};

export const buildHolderChartRows = (holders) => {
  const holderNumberRows = Array.isArray(holders?.holder_number) ? holders.holder_number : [];
  const top10Rows = Array.isArray(holders?.top10_holders) ? holders.top10_holders : [];
  const top10FloatRows = Array.isArray(holders?.top10_floatholders) ? holders.top10_floatholders : [];

  const aggregateRatio = (rows) => rows.reduce((map, item) => {
    const key = item.end_date || item.ann_date;
    if (!key) return map;
    map.set(key, round((map.get(key) ?? 0) + (toNum(item.hold_ratio) ?? 0)));
    return map;
  }, new Map());

  const top10RatioMap = aggregateRatio(top10Rows);
  const top10FloatRatioMap = aggregateRatio(top10FloatRows);
  const baseMap = new Map();

  holderNumberRows.forEach((item) => {
    const key = item.end_date || item.ann_date;
    if (!key) return;
    baseMap.set(key, {
      end_date: item.end_date || key,
      ann_date: item.ann_date || null,
      holder_num: toNum(item.holder_num),
      top10_ratio: top10RatioMap.get(key) ?? null,
      top10_float_ratio: top10FloatRatioMap.get(key) ?? null,
    });
  });

  [...top10RatioMap.keys(), ...top10FloatRatioMap.keys()].forEach((key) => {
    if (!baseMap.has(key)) {
      baseMap.set(key, {
        end_date: key,
        ann_date: null,
        holder_num: null,
        top10_ratio: top10RatioMap.get(key) ?? null,
        top10_float_ratio: top10FloatRatioMap.get(key) ?? null,
      });
    }
  });

  return [...baseMap.values()].sort((a, b) => String(a.end_date).localeCompare(String(b.end_date))).slice(-12);
};

export const buildHolderTrendOption = (rows) => ({
  backgroundColor: "transparent",
  animation: false,
  legend: {
    top: 8,
    textStyle: { color: "#475569", fontSize: 12 },
    data: ["股东人数", "前十大股东集中度", "前十大流通股东集中度"],
  },
  tooltip: {
    trigger: "axis",
    axisPointer: { type: "cross" },
    formatter: (params) => {
      if (!params?.length) return "";
      const row = rows[params[0].dataIndex];
      const lines = [formatDate(row?.end_date)];
      if (row?.ann_date) lines.push(`公告日: ${formatDate(row.ann_date)}`);
      params.forEach((item, index) => {
        const kind = index === 0 ? "amount" : "percent";
        lines.push(`${item.marker}${item.seriesName}: ${formatTooltipMetric(item.value, kind)}`);
      });
      return lines.join("<br/>");
    },
  },
  grid: { left: 56, right: 72, top: 44, bottom: 40 },
  xAxis: {
    type: "category",
    data: rows.map((row) => formatDate(row.end_date)),
    axisLine: { lineStyle: { color: "#cbd5e1" } },
    axisLabel: { color: "#64748b" },
  },
  yAxis: [
    {
      type: "value",
      name: "人数",
      axisLabel: { color: "#64748b", formatter: formatAxisUnit },
      splitLine: { lineStyle: { color: "rgba(148, 163, 184, 0.16)" } },
    },
    {
      type: "value",
      name: "集中度",
      axisLabel: { color: "#64748b", formatter: (value) => `${round(value)?.toFixed(0)}%` },
      splitLine: { show: false },
    },
  ],
  series: [
    {
      name: "股东人数",
      type: "line",
      data: rows.map((row) => row.holder_num),
      symbol: "circle",
      lineStyle: { color: "#2563eb", width: 2 },
    },
    {
      name: "前十大股东集中度",
      type: "line",
      yAxisIndex: 1,
      data: rows.map((row) => row.top10_ratio),
      symbol: "circle",
      lineStyle: { color: "#14b8a6", width: 2 },
    },
    {
      name: "前十大流通股东集中度",
      type: "line",
      yAxisIndex: 1,
      data: rows.map((row) => row.top10_float_ratio),
      symbol: "circle",
      lineStyle: { color: "#f59e0b", width: 2 },
    },
  ],
});

export const buildChipChartRows = (chips) => {
  const perfRows = Array.isArray(chips?.cyq_perf) ? chips.cyq_perf : [];
  const chipRows = Array.isArray(chips?.cyq_chips) ? chips.cyq_chips : [];
  const perf = [...perfRows]
    .sort((a, b) => String(a.trade_date).localeCompare(String(b.trade_date)))
    .slice(-120)
    .map((item) => ({
      ...item,
      trade_date: item.trade_date,
      weight_avg: toNum(item.weight_avg),
      cost_focus: toNum(item.cost_focus),
      profit_ratio: toNum(item.profit_ratio),
    }));
  const latestTradeDate = [...chipRows]
    .map((item) => item.trade_date)
    .filter(Boolean)
    .sort()
    .at(-1) ?? null;
  const distribution = latestTradeDate
    ? chipRows
        .filter((item) => item.trade_date === latestTradeDate)
        .map((item) => ({ ...item, price: toNum(item.price), percent: toNum(item.percent) }))
        .sort((a, b) => (a.price ?? 0) - (b.price ?? 0))
        .slice(0, 120)
    : [];
  return { perf, distribution, latestTradeDate };
};

export const buildChipPerfChartOption = (rows) => ({
  backgroundColor: "transparent",
  animation: false,
  legend: {
    top: 8,
    textStyle: { color: "#475569", fontSize: 12 },
    data: ["加权成本", "成本集中度", "获利比例"],
  },
  tooltip: {
    trigger: "axis",
    axisPointer: { type: "cross" },
  },
  grid: { left: 56, right: 64, top: 44, bottom: 40 },
  xAxis: {
    type: "category",
    data: rows.map((row) => formatDate(row.trade_date)),
    axisLine: { lineStyle: { color: "#cbd5e1" } },
    axisLabel: { color: "#64748b" },
  },
  yAxis: [
    {
      type: "value",
      name: "价格",
      axisLabel: { color: "#64748b" },
      splitLine: { lineStyle: { color: "rgba(148, 163, 184, 0.16)" } },
    },
    {
      type: "value",
      name: "比例",
      axisLabel: { color: "#64748b", formatter: (value) => `${round(value)?.toFixed(0)}%` },
      splitLine: { show: false },
    },
  ],
  series: [
    {
      name: "加权成本",
      type: "line",
      data: rows.map((row) => row.weight_avg),
      symbol: "none",
      lineStyle: { color: "#2563eb", width: 2 },
    },
    {
      name: "成本集中度",
      type: "line",
      yAxisIndex: 1,
      data: rows.map((row) => row.cost_focus),
      symbol: "none",
      lineStyle: { color: "#14b8a6", width: 2 },
    },
    {
      name: "获利比例",
      type: "line",
      yAxisIndex: 1,
      data: rows.map((row) => row.profit_ratio),
      symbol: "none",
      lineStyle: { color: "#f59e0b", width: 2 },
    },
  ],
});

export const buildChipDistributionOption = (rows, latestTradeDate) => ({
  backgroundColor: "transparent",
  animation: false,
  tooltip: {
    trigger: "axis",
    axisPointer: { type: "shadow" },
    formatter: (params) => {
      if (!params?.length) return "";
      const row = rows[params[0].dataIndex];
      return [
        `${latestTradeDate ? formatDate(latestTradeDate) : "最新分布"}`,
        `${params[0].marker}价格: ${row?.price ?? "-"}`,
        `占比: ${formatTooltipMetric(row?.percent, "percent")}`,
      ].join("<br/>");
    },
  },
  grid: { left: 56, right: 32, top: 24, bottom: 40 },
  xAxis: {
    type: "category",
    data: rows.map((row) => row.price ?? "-"),
    axisLine: { lineStyle: { color: "#cbd5e1" } },
    axisLabel: { color: "#64748b", rotate: rows.length > 24 ? 45 : 0 },
  },
  yAxis: {
    type: "value",
    axisLabel: { color: "#64748b", formatter: (value) => `${round(value)?.toFixed(0)}%` },
    splitLine: { lineStyle: { color: "rgba(148, 163, 184, 0.16)" } },
  },
  series: [
    {
      name: "筹码占比",
      type: "bar",
      data: rows.map((row) => row.percent),
      itemStyle: { color: "#8b5cf6" },
    },
  ],
});

export const buildCrossBorderHoldRows = (flows) => {
  const hkRows = Array.isArray(flows?.hk_hold) ? flows.hk_hold : [];
  const ccassRows = Array.isArray(flows?.ccass_hold) ? flows.ccass_hold : [];
  const map = new Map();

  hkRows.forEach((item) => {
    const key = item.trade_date;
    if (!key) return;
    const current = map.get(key) || {
      trade_date: key,
      hk_hold_vol: 0,
      hk_hold_ratio: 0,
      ccass_hold_vol: 0,
      ccass_hold_ratio: 0,
    };
    current.hk_hold_vol = round((current.hk_hold_vol ?? 0) + (toNum(item.vol) ?? 0));
    current.hk_hold_ratio = round((current.hk_hold_ratio ?? 0) + (toNum(item.ratio) ?? 0));
    map.set(key, current);
  });

  ccassRows.forEach((item) => {
    const key = item.trade_date;
    if (!key) return;
    const current = map.get(key) || {
      trade_date: key,
      hk_hold_vol: 0,
      hk_hold_ratio: 0,
      ccass_hold_vol: 0,
      ccass_hold_ratio: 0,
    };
    current.ccass_hold_vol = round((current.ccass_hold_vol ?? 0) + (toNum(item.vol) ?? 0));
    current.ccass_hold_ratio = round((current.ccass_hold_ratio ?? 0) + (toNum(item.hold_ratio) ?? 0));
    map.set(key, current);
  });

  return [...map.values()].sort((a, b) => String(a.trade_date).localeCompare(String(b.trade_date))).slice(-120);
};

export const buildCrossBorderHoldOption = (rows) => ({
  backgroundColor: "transparent",
  animation: false,
  legend: {
    top: 8,
    textStyle: { color: "#475569", fontSize: 12 },
    data: ["港股通持股", "CCASS 持股", "港股通持股比例", "CCASS 持股比例"],
  },
  tooltip: {
    trigger: "axis",
    axisPointer: { type: "cross" },
    formatter: (params) => {
      if (!params?.length) return "";
      const lines = [formatDate(rows[params[0].dataIndex]?.trade_date)];
      params.forEach((item, index) => {
        const kind = index < 2 ? "amount" : "percent";
        lines.push(`${item.marker}${item.seriesName}: ${formatTooltipMetric(item.value, kind)}`);
      });
      return lines.join("<br/>");
    },
  },
  grid: { left: 56, right: 72, top: 44, bottom: 40 },
  xAxis: {
    type: "category",
    data: rows.map((row) => formatDate(row.trade_date)),
    axisLine: { lineStyle: { color: "#cbd5e1" } },
    axisLabel: { color: "#64748b" },
  },
  yAxis: [
    {
      type: "value",
      name: "持股量",
      axisLabel: { color: "#64748b", formatter: formatAxisUnit },
      splitLine: { lineStyle: { color: "rgba(148, 163, 184, 0.16)" } },
    },
    {
      type: "value",
      name: "持股比例",
      axisLabel: { color: "#64748b", formatter: (value) => `${round(value)?.toFixed(1)}%` },
      splitLine: { show: false },
    },
  ],
  series: [
    {
      name: "港股通持股",
      type: "bar",
      data: rows.map((row) => row.hk_hold_vol),
      itemStyle: { color: "#2563eb" },
    },
    {
      name: "CCASS 持股",
      type: "bar",
      data: rows.map((row) => row.ccass_hold_vol),
      itemStyle: { color: "#8b5cf6" },
    },
    {
      name: "港股通持股比例",
      type: "line",
      yAxisIndex: 1,
      data: rows.map((row) => row.hk_hold_ratio),
      symbol: "none",
      lineStyle: { color: "#14b8a6", width: 2 },
    },
    {
      name: "CCASS 持股比例",
      type: "line",
      yAxisIndex: 1,
      data: rows.map((row) => row.ccass_hold_ratio),
      symbol: "none",
      lineStyle: { color: "#f59e0b", width: 2 },
    },
  ],
});

export const buildEventTimelineRows = (events) => {
  const suspendRows = Array.isArray(events?.suspend) ? events.suspend : [];
  const surveyRows = Array.isArray(events?.institution_surveys) ? events.institution_surveys : [];
  return [
    ...surveyRows.map((item) => ({
      kind: "survey",
      date: item.surv_date,
      title: item.title || "机构调研",
      subtitle: item.surv_type || "调研",
      detail: item.rece_org || "-",
    })),
    ...suspendRows.map((item) => ({
      kind: "suspend",
      date: item.trade_date,
      title: item.reason || "停复牌事件",
      subtitle: item.suspend_type || "停牌",
      detail: item.suspend_timing || "-",
    })),
  ]
    .filter((item) => item.date)
    .sort((a, b) => String(b.date).localeCompare(String(a.date)))
    .slice(0, 30);
};

export const buildDividendChartRows = (dividends) => {
  const rows = Array.isArray(dividends?.items) ? dividends.items : [];
  return [...rows]
    .map((item) => ({
      ...item,
      chart_date: item.ex_date || item.ann_date || item.end_date,
      cash_div: toNum(item.cash_div),
      stk_div: toNum(item.stk_div),
    }))
    .filter((item) => item.chart_date)
    .sort((a, b) => String(a.chart_date).localeCompare(String(b.chart_date)))
    .slice(-16);
};

export const buildDividendChartOption = (rows) => ({
  backgroundColor: "transparent",
  animation: false,
  legend: {
    top: 8,
    textStyle: { color: "#475569", fontSize: 12 },
    data: ["现金分红", "送股"],
  },
  tooltip: {
    trigger: "axis",
    axisPointer: { type: "shadow" },
    formatter: (params) => {
      if (!params?.length) return "";
      const row = rows[params[0].dataIndex];
      return [
        formatDate(row?.chart_date),
        `${params[0].marker}现金分红: ${formatTooltipMetric(row?.cash_div, "amount")}`,
        `${params[1].marker}送股: ${formatTooltipMetric(row?.stk_div, "amount")}`,
      ].join("<br/>");
    },
  },
  grid: { left: 56, right: 32, top: 44, bottom: 40 },
  xAxis: {
    type: "category",
    data: rows.map((row) => formatDate(row.chart_date)),
    axisLine: { lineStyle: { color: "#cbd5e1" } },
    axisLabel: { color: "#64748b" },
  },
  yAxis: {
    type: "value",
    axisLabel: { color: "#64748b" },
    splitLine: { lineStyle: { color: "rgba(148, 163, 184, 0.16)" } },
  },
  series: [
    {
      name: "现金分红",
      type: "bar",
      data: rows.map((row) => row.cash_div),
      itemStyle: { color: "#22c55e" },
    },
    {
      name: "送股",
      type: "line",
      data: rows.map((row) => row.stk_div),
      symbol: "circle",
      lineStyle: { color: "#2563eb", width: 2 },
    },
  ],
});

export const buildMoneyflowBreakdownOption = (rows) => ({
  backgroundColor: "transparent",
  animation: false,
  legend: {
    top: 8,
    textStyle: { color: "#475569", fontSize: 12 },
    data: ["小单买入", "中单买入", "大单买入", "特大单买入"],
  },
  tooltip: {
    trigger: "axis",
    axisPointer: { type: "shadow" },
    formatter: (params) => {
      if (!params?.length) return "";
      const lines = [formatDate(rows[params[0].dataIndex]?.trade_date)];
      params.forEach((item) => lines.push(`${item.marker}${item.seriesName}: ${formatTooltipMetric(item.value, "amount")}`));
      return lines.join("<br/>");
    },
  },
  grid: { left: 56, right: 32, top: 44, bottom: 40 },
  xAxis: {
    type: "category",
    data: rows.map((row) => formatDate(row.trade_date)),
    axisLine: { lineStyle: { color: "#cbd5e1" } },
    axisLabel: { color: "#64748b" },
  },
  yAxis: {
    type: "value",
    axisLabel: { color: "#64748b", formatter: formatAxisUnit },
    splitLine: { lineStyle: { color: "rgba(148, 163, 184, 0.16)" } },
  },
  series: [
    { name: "小单买入", type: "bar", stack: "moneyflow", data: rows.map((row) => toNum(row.buy_sm_amount)), itemStyle: { color: "#94a3b8" } },
    { name: "中单买入", type: "bar", stack: "moneyflow", data: rows.map((row) => toNum(row.buy_md_amount)), itemStyle: { color: "#38bdf8" } },
    { name: "大单买入", type: "bar", stack: "moneyflow", data: rows.map((row) => toNum(row.buy_lg_amount)), itemStyle: { color: "#14b8a6" } },
    { name: "特大单买入", type: "bar", stack: "moneyflow", data: rows.map((row) => toNum(row.buy_elg_amount)), itemStyle: { color: "#f59e0b" } },
  ],
});

export const buildMoneyflowChartOption = (rows) => ({
  backgroundColor: "transparent",
  animation: false,
  tooltip: {
    trigger: "axis",
    axisPointer: { type: "shadow" },
    formatter: (params) => {
      if (!params?.length) return "";
      const row = rows[params[0].dataIndex];
      return [
        formatDate(row?.trade_date),
        `${params[0].marker}净流入额: ${formatTooltipMetric(row?.net_mf_amount, "amount")}`,
      ].join("<br/>");
    },
  },
  grid: { left: 56, right: 32, top: 24, bottom: 40 },
  xAxis: {
    type: "category",
    data: rows.map((row) => formatDate(row.trade_date)),
    axisLine: { lineStyle: { color: "#cbd5e1" } },
    axisLabel: { color: "#64748b" },
  },
  yAxis: {
    type: "value",
    axisLabel: { color: "#64748b", formatter: formatAxisUnit },
    splitLine: { lineStyle: { color: "rgba(148, 163, 184, 0.16)" } },
  },
  series: [
    {
      name: "净流入额",
      type: "bar",
      data: rows.map((row) => ({
        value: toNum(row.net_mf_amount),
        itemStyle: { color: (toNum(row.net_mf_amount) ?? 0) >= 0 ? "#22c55e" : "#ef4444" },
      })),
    },
  ],
});

export const buildMarginChartOption = (rows) => ({
  backgroundColor: "transparent",
  animation: false,
  legend: {
    top: 8,
    textStyle: { color: "#475569", fontSize: 12 },
    data: ["融资余额", "融券余额", "两融余额"],
  },
  tooltip: {
    trigger: "axis",
    axisPointer: { type: "cross" },
    formatter: (params) => {
      if (!params?.length) return "";
      const row = rows[params[0].dataIndex];
      const lines = [formatDate(row?.trade_date)];
      params.forEach((item) => lines.push(`${item.marker}${item.seriesName}: ${formatTooltipMetric(item.value, "amount")}`));
      return lines.join("<br/>");
    },
  },
  grid: { left: 56, right: 32, top: 44, bottom: 40 },
  xAxis: {
    type: "category",
    data: rows.map((row) => formatDate(row.trade_date)),
    axisLine: { lineStyle: { color: "#cbd5e1" } },
    axisLabel: { color: "#64748b" },
  },
  yAxis: {
    type: "value",
    axisLabel: { color: "#64748b", formatter: formatAxisUnit },
    splitLine: { lineStyle: { color: "rgba(148, 163, 184, 0.16)" } },
  },
  series: [
    {
      name: "融资余额",
      type: "line",
      data: rows.map((row) => toNum(row.rzye)),
      symbol: "none",
      lineStyle: { color: "#2563eb", width: 2 },
    },
    {
      name: "融券余额",
      type: "line",
      data: rows.map((row) => toNum(row.rqye)),
      symbol: "none",
      lineStyle: { color: "#8b5cf6", width: 2 },
    },
    {
      name: "两融余额",
      type: "line",
      data: rows.map((row) => toNum(row.rzrqye)),
      symbol: "none",
      lineStyle: { color: "#f59e0b", width: 2 },
    },
  ],
});
