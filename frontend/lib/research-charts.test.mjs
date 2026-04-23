import test from "node:test";
import assert from "node:assert/strict";

import {
  buildFinancialChartRows,
  buildFinancialChartOption,
  buildFinancialSummaryStats,
  buildFlowChartRows,
  buildDividendChartRows,
  buildDividendChartOption,
  buildHolderChartRows,
  buildHolderTrendOption,
  buildChipChartRows,
  buildCrossBorderHoldRows,
  buildCrossBorderHoldOption,
  buildEventTimelineRows,
  buildMoneyflowBreakdownOption,
  formatAxisUnit,
  formatTooltipMetric,
} from "./research-charts.mjs";

const financialSample = {
  indicators: [
    { end_date: "20231231", ann_date: "20240320", roe: "12.5", roa: "5.1", grossprofit_margin: "31.2", debt_to_assets: "48.3" },
    { end_date: "20240331", ann_date: "20240430", roe: "3.2", roa: "1.4", grossprofit_margin: "29.1", debt_to_assets: "47.8" },
    { end_date: "20240630", ann_date: "20240825", roe: "6.6", roa: "2.8", grossprofit_margin: "30.6", debt_to_assets: "47.2" },
    { end_date: "20240930", ann_date: "20241029", roe: "9.1", roa: "4.1", grossprofit_margin: "30.4", debt_to_assets: "46.9" },
    { end_date: "20241231", ann_date: "20250320", roe: "13.2", roa: "5.4", grossprofit_margin: "31.9", debt_to_assets: "46.2" },
    { end_date: "20250331", ann_date: "20250428", roe: "3.6", roa: "1.6", grossprofit_margin: "32.4", debt_to_assets: "45.5" },
  ],
  income: [
    { end_date: "20231231", ann_date: "20240320", revenue: "1000000000", n_income: "220000000" },
    { end_date: "20240331", ann_date: "20240430", revenue: "220000000", n_income: "48000000" },
    { end_date: "20240630", ann_date: "20240825", revenue: "510000000", n_income: "116000000" },
    { end_date: "20240930", ann_date: "20241029", revenue: "770000000", n_income: "168000000" },
    { end_date: "20241231", ann_date: "20250320", revenue: "1100000000", n_income: "240000000" },
    { end_date: "20250331", ann_date: "20250428", revenue: "260000000", n_income: "58000000" },
  ],
  cashflow: [
    { end_date: "20231231", ann_date: "20240320", n_cashflow_act: "180000000" },
    { end_date: "20240331", ann_date: "20240430", n_cashflow_act: "36000000" },
    { end_date: "20240630", ann_date: "20240825", n_cashflow_act: "89000000" },
    { end_date: "20240930", ann_date: "20241029", n_cashflow_act: "141000000" },
    { end_date: "20241231", ann_date: "20250320", n_cashflow_act: "190000000" },
    { end_date: "20250331", ann_date: "20250428", n_cashflow_act: "42000000" },
  ],
};

test("quarterly financial rows keep recent quarters and compute yoy and ttm values", () => {
  const rows = buildFinancialChartRows(financialSample, "quarterly");

  const current = rows.at(-1);
  assert.equal(current.end_date, "20250331");
  assert.equal(current.revenue, 260000000);
  assert.equal(current.revenue_yoy, 18.18);
  assert.equal(current.n_income_yoy, 20.83);
  assert.equal(current.n_cashflow_act_yoy, 16.67);
  assert.equal(current.revenue_ttm, 1140000000);
  assert.equal(current.n_income_ttm, 250000000);
  assert.equal(current.n_cashflow_act_ttm, 196000000);
});

test("annual financial rows keep only year-end reports", () => {
  const rows = buildFinancialChartRows(financialSample, "annual");

  assert.equal(rows.length, 2);
  assert.equal(rows.at(-1).end_date, "20241231");
  assert.equal(rows.at(-1).revenue, 1100000000);
});

test("financial chart option switches metric labels for yoy mode", () => {
  const rows = buildFinancialChartRows(financialSample, "quarterly");
  const option = buildFinancialChartOption(rows, "quarterly", "yoy");

  assert.equal(option.yAxis[0].name, "同比增速");
  assert.equal(option.series[0].name, "营收同比");
  assert.equal(option.series[0].data.at(-1), 18.18);
  assert.equal(option.series[3].name, "ROE");
});

test("financial summary stats expose latest yoy and ttm snapshot", () => {
  const rows = buildFinancialChartRows(financialSample, "quarterly");
  const summary = buildFinancialSummaryStats(rows);

  assert.equal(summary.latest_period, "20250331");
  assert.equal(summary.revenue_yoy, 18.18);
  assert.equal(summary.n_income_yoy, 20.83);
  assert.equal(summary.revenue_ttm, 1140000000);
  assert.equal(summary.n_income_ttm, 250000000);
});

test("flow rows slice by requested window", () => {
  const flows = {
    moneyflow_dc: [
      { trade_date: "20250102", net_mf_amount: "1" },
      { trade_date: "20250103", net_mf_amount: "2" },
      { trade_date: "20250106", net_mf_amount: "3" },
    ],
    margin_detail: [
      { trade_date: "20250102", rzye: "10", rqye: "1", rzrqye: "11" },
      { trade_date: "20250103", rzye: "11", rqye: "2", rzrqye: "13" },
      { trade_date: "20250106", rzye: "12", rqye: "3", rzrqye: "15" },
    ],
  };

  const rows = buildFlowChartRows(flows, 2);
  assert.deepEqual(rows.moneyflow.map((item) => item.trade_date), ["20250103", "20250106"]);
  assert.deepEqual(rows.margin.map((item) => item.trade_date), ["20250103", "20250106"]);
});

test("holder chart rows aggregate top10 concentration by report period", () => {
  const holders = {
    holder_number: [
      { end_date: "20241231", ann_date: "20250320", holder_num: "120000" },
      { end_date: "20250331", ann_date: "20250425", holder_num: "118000" },
    ],
    top10_holders: [
      { end_date: "20250331", hold_ratio: "12.3" },
      { end_date: "20250331", hold_ratio: "8.7" },
      { end_date: "20241231", hold_ratio: "11.1" },
    ],
    top10_floatholders: [
      { end_date: "20250331", hold_ratio: "9.5" },
      { end_date: "20250331", hold_ratio: "7.5" },
      { end_date: "20241231", hold_ratio: "8.0" },
    ],
  };

  const rows = buildHolderChartRows(holders);
  assert.equal(rows.length, 2);
  assert.equal(rows.at(-1).end_date, "20250331");
  assert.equal(rows.at(-1).holder_num, 118000);
  assert.equal(rows.at(-1).top10_ratio, 21);
  assert.equal(rows.at(-1).top10_float_ratio, 17);

  const option = buildHolderTrendOption(rows);
  assert.equal(option.series[0].name, "股东人数");
  assert.equal(option.series[1].name, "前十大股东集中度");
});

test("chip chart rows keep latest distribution snapshot", () => {
  const chips = {
    cyq_perf: [
      { trade_date: "20250313", weight_avg: "10.1", cost_focus: "22.3", profit_ratio: "54.2" },
      { trade_date: "20250314", weight_avg: "10.4", cost_focus: "23.1", profit_ratio: "56.8" },
    ],
    cyq_chips: [
      { trade_date: "20250313", price: "10.0", percent: "3.2" },
      { trade_date: "20250314", price: "10.1", percent: "5.1" },
      { trade_date: "20250314", price: "10.3", percent: "6.6" },
    ],
  };

  const rows = buildChipChartRows(chips);
  assert.equal(rows.latestTradeDate, "20250314");
  assert.equal(rows.perf.length, 2);
  assert.deepEqual(rows.distribution.map((item) => item.price), [10.1, 10.3]);
});

test("cross-border hold rows aggregate hk hold and ccass by trade date", () => {
  const flows = {
    hk_hold: [
      { trade_date: "20250313", vol: "1000", ratio: "1.2" },
      { trade_date: "20250314", vol: "1200", ratio: "1.4" },
      { trade_date: "20250314", vol: "800", ratio: "0.6" },
    ],
    ccass_hold: [
      { trade_date: "20250313", vol: "500", hold_ratio: "0.7" },
      { trade_date: "20250314", vol: "700", hold_ratio: "0.9" },
    ],
  };

  const rows = buildCrossBorderHoldRows(flows);
  assert.equal(rows.length, 2);
  assert.equal(rows.at(-1).hk_hold_vol, 2000);
  assert.equal(rows.at(-1).hk_hold_ratio, 2);
  assert.equal(rows.at(-1).ccass_hold_vol, 700);
  assert.equal(rows.at(-1).ccass_hold_ratio, 0.9);

  const option = buildCrossBorderHoldOption(rows);
  assert.equal(option.series[0].name, "港股通持股");
  assert.equal(option.series[3].name, "CCASS 持股比例");
});

test("event timeline rows merge suspend and survey events in reverse chronological order", () => {
  const events = {
    suspend: [
      { trade_date: "20250312", suspend_type: "停牌", reason: "重大事项" },
    ],
    institution_surveys: [
      { surv_date: "20250314", rece_org: "券商联合调研", title: "业绩说明会", surv_type: "特定对象调研" },
    ],
  };

  const rows = buildEventTimelineRows(events);
  assert.equal(rows.length, 2);
  assert.equal(rows[0].kind, "survey");
  assert.equal(rows[0].title, "业绩说明会");
  assert.equal(rows[1].kind, "suspend");
  assert.equal(rows[1].subtitle, "停牌");
});

test("dividend chart rows keep recent distributions sorted by ex-date", () => {
  const dividends = {
    items: [
      { ex_date: "20240510", ann_date: "20240420", cash_div: "0.8", stk_div: "0.1" },
      { ex_date: "20250515", ann_date: "20250422", cash_div: "1.2", stk_div: "0.0" },
    ],
  };
  const rows = buildDividendChartRows(dividends);
  assert.equal(rows.length, 2);
  assert.equal(rows.at(-1).cash_div, 1.2);
  const option = buildDividendChartOption(rows);
  assert.equal(option.series[0].name, "现金分红");
  assert.equal(option.series[1].name, "送股");
});

test("moneyflow breakdown option maps size buckets into stacked bars", () => {
  const option = buildMoneyflowBreakdownOption([
    { trade_date: "20250313", buy_sm_amount: "10", buy_md_amount: "20", buy_lg_amount: "30", buy_elg_amount: "40" },
    { trade_date: "20250314", buy_sm_amount: "11", buy_md_amount: "21", buy_lg_amount: "31", buy_elg_amount: "41" },
  ]);
  assert.equal(option.series.length, 4);
  assert.equal(option.series[0].name, "小单买入");
  assert.equal(option.series[3].data.at(-1), 41);
});

test("unit formatters emit chinese large number units", () => {
  assert.equal(formatAxisUnit(1250000000), "12.50亿");
  assert.equal(formatAxisUnit(320000), "32.00万");
  assert.equal(formatTooltipMetric(1250000000, "amount"), "12.50亿");
  assert.equal(formatTooltipMetric(18.236, "percent"), "18.24%");
});
