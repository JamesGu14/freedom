#!/usr/bin/env python3
"""Freedom Quant Platform MCP Server

Exposes Freedom's A-share quantitative data as MCP tools for AI agents.

Environment variables:
  FREEDOM_API_BASE_URL  API base URL (default: http://localhost:9000/api)
  FREEDOM_API_TOKEN     Bearer token for authentication
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional

import httpx
from mcp.server.fastmcp import FastMCP

API_BASE = os.getenv("FREEDOM_API_BASE_URL", "http://localhost:9000/api").rstrip("/")
API_TOKEN = os.getenv("FREEDOM_API_TOKEN", "")

mcp = FastMCP("Freedom Quant")


def _headers() -> dict[str, str]:
    h = {"Accept": "application/json", "Content-Type": "application/json"}
    if API_TOKEN:
        h["Authorization"] = f"Bearer {API_TOKEN}"
    return h


async def _request(method: str, path: str, params: dict[str, Any] | None = None, json_data: dict[str, Any] | None = None) -> Any:
    clean_params = {k: v for k, v in (params or {}).items() if v is not None}
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.request(
            method, f"{API_BASE}{path}",
            params=clean_params,
            json=json_data,
            headers=_headers(),
        )
        r.raise_for_status()
        body = r.json()
        return body.get("data", body)


async def _get(path: str, params: dict[str, Any] | None = None) -> Any:
    return await _request("GET", path, params)


async def _post(path: str, json_data: dict[str, Any] | None = None) -> Any:
    return await _request("POST", path, json_data=json_data)


async def _patch(path: str, json_data: dict[str, Any] | None = None) -> Any:
    return await _request("PATCH", path, json_data=json_data)


async def _delete(path: str) -> Any:
    return await _request("DELETE", path)


def _fmt(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


# ── 1. 基础信息 ───────────────────────────────────────────────────────────────

@mcp.tool()
async def get_latest_trade_date(exchange: str = "SSE") -> str:
    """获取最新交易日期。

    Args:
        exchange: 交易所代码，SSE（上交所）或 SZSE（深交所），默认 SSE
    """
    data = await _get("/trade-calendar/latest-trade-date", {"exchange": exchange})
    return _fmt(data)


@mcp.tool()
async def get_trade_calendar(
    start_date: str,
    end_date: str,
    is_open: Optional[bool] = None,
    exchange: str = "SSE",
) -> str:
    """查询交易日历，判断某段时间内哪些天是交易日。

    Args:
        start_date: 开始日期，格式 YYYYMMDD 或 YYYY-MM-DD
        end_date: 结束日期，格式 YYYYMMDD 或 YYYY-MM-DD
        is_open: True 只返回交易日，False 只返回非交易日，None 返回全部
        exchange: 交易所，SSE 或 SZSE
    """
    data = await _get("/trade-calendar", {
        "start_date": start_date,
        "end_date": end_date,
        "is_open": is_open,
        "exchange": exchange,
    })
    return _fmt(data)


@mcp.tool()
async def search_stocks(q: str, limit: int = 20) -> str:
    """按关键词搜索股票，支持股票代码、简称或全称模糊匹配。

    Args:
        q: 搜索关键词，如 "贵州茅台"、"600519" 或 "MAOTAI"
        limit: 最多返回条数，默认 20，最大 200
    """
    data = await _get("/stocks/search", {"q": q, "limit": limit})
    return _fmt(data)


@mcp.tool()
async def list_stocks(
    market: Optional[str] = None,
    exchange: Optional[str] = None,
    page: int = 1,
    page_size: int = 200,
) -> str:
    """列出 A 股股票基础信息，支持按市场和交易所筛选。

    Args:
        market: 市场板块，可选 主板/创业板/科创板，或英文 MAIN/GEM/STAR
        exchange: 交易所，SSE（上交所）或 SZSE（深交所）或 BSE（北交所）
        page: 页码，默认 1
        page_size: 每页条数，默认 200，最大 2000
    """
    data = await _get("/stocks/basic", {
        "market": market,
        "exchange": exchange,
        "page": page,
        "page_size": page_size,
    })
    return _fmt(data)


@mcp.tool()
async def get_stock_basic(ts_code: str) -> str:
    """获取单只股票的基础信息（名称、行业、市场、上市日期等）。

    Args:
        ts_code: 股票代码，格式 XXXXXX.SH 或 XXXXXX.SZ，如 600519.SH
    """
    data = await _get(f"/stocks/basic/{ts_code}")
    return _fmt(data)


@mcp.tool()
async def list_industries() -> str:
    """获取所有行业分类列表。"""
    data = await _get("/stocks/industries")
    return _fmt(data)


@mcp.tool()
async def list_stock_groups() -> str:
    """获取用户的股票分组（自选股列表）。"""
    data = await _get("/stock-groups")
    return _fmt(data)


@mcp.tool()
async def get_stock_group(group_id: str) -> str:
    """获取指定股票分组的详情和成员股票。

    Args:
        group_id: 分组 ID
    """
    data = await _get(f"/stock-groups/{group_id}")
    return _fmt(data)


@mcp.tool()
async def create_stock_group(name: str, description: Optional[str] = None) -> str:
    """创建一个新的股票分组（自选股列表）。

    Args:
        name: 分组名称
        description: 分组描述
    """
    data = await _post("/stock-groups", {"name": name, "description": description})
    return _fmt(data)


@mcp.tool()
async def add_stock_to_group(group_id: str, ts_code: str) -> str:
    """向股票分组中添加股票。

    Args:
        group_id: 分组 ID
        ts_code: 股票代码，如 600519.SH
    """
    data = await _post(f"/stock-groups/{group_id}/stocks", {"ts_code": ts_code})
    return _fmt(data)


@mcp.tool()
async def remove_stock_from_group(group_id: str, ts_code: str) -> str:
    """从股票分组中移除股票。

    Args:
        group_id: 分组 ID
        ts_code: 股票代码，如 600519.SH
    """
    data = await _delete(f"/stock-groups/{group_id}/stocks/{ts_code}")
    return _fmt(data)


# ── 2. 行情数据 ───────────────────────────────────────────────────────────────

@mcp.tool()
async def get_stock_daily(
    ts_code: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    adj: str = "qfq",
) -> str:
    """获取股票日线行情（开高低收、成交量、涨跌幅）。

    Args:
        ts_code: 股票代码，如 600519.SH
        start_date: 开始日期，格式 YYYYMMDD，不填则返回全部历史
        end_date: 结束日期，格式 YYYYMMDD
        adj: 复权方式，qfq（前复权，默认）/hfq（后复权）/none（不复权）
    """
    data = await _get(f"/stocks/{ts_code}/daily", {
        "start_date": start_date,
        "end_date": end_date,
        "adj": adj,
    })
    return _fmt(data)


@mcp.tool()
async def get_stock_daily_recent(ts_code: str, n: int = 60, adj: str = "qfq") -> str:
    """获取股票最近 N 个交易日的日线数据（最常用的行情查询方式）。

    Args:
        ts_code: 股票代码，如 000001.SZ
        n: 最近 N 个交易日，默认 60，最大 4000
        adj: 复权方式，qfq（前复权，默认）/hfq/none
    """
    data = await _get(f"/stocks/{ts_code}/daily/recent", {"n": n, "adj": adj})
    return _fmt(data)


@mcp.tool()
async def get_daily_snapshot(
    trade_date: Optional[str] = None,
    ts_codes: Optional[str] = None,
    page: int = 1,
    page_size: int = 500,
) -> str:
    """获取某一交易日全市场（或指定股票列表）的行情快照。

    Args:
        trade_date: 交易日期，格式 YYYYMMDD，不填则取最近交易日
        ts_codes: 股票代码列表，逗号分隔，如 "600519.SH,000858.SZ"，不填则返回全市场
        page: 页码
        page_size: 每页条数，默认 500，最大 5000
    """
    data = await _get("/stocks/daily/snapshot", {
        "trade_date": trade_date,
        "ts_codes": ts_codes,
        "page": page,
        "page_size": page_size,
    })
    return _fmt(data)


@mcp.tool()
async def get_stock_daily_basic(
    ts_code: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> str:
    """获取股票每日估值与市值数据（PE、PB、PS、市值、换手率、量比等）。

    Args:
        ts_code: 股票代码，如 600519.SH
        start_date: 开始日期，格式 YYYYMMDD
        end_date: 结束日期，格式 YYYYMMDD
    """
    data = await _get(f"/stocks/{ts_code}/daily-basic", {
        "start_date": start_date,
        "end_date": end_date,
    })
    return _fmt(data)


@mcp.tool()
async def screen_stocks_by_valuation(
    trade_date: Optional[str] = None,
    pe_ttm_max: Optional[float] = None,
    pb_max: Optional[float] = None,
    total_mv_min: Optional[float] = None,
    total_mv_max: Optional[float] = None,
    dv_ratio_min: Optional[float] = None,
    page: int = 1,
    page_size: int = 200,
) -> str:
    """按估值指标筛选全市场股票（PE、PB、市值、股息率组合筛选）。

    Args:
        trade_date: 交易日期，格式 YYYYMMDD，不填则取最近交易日
        pe_ttm_max: PE（TTM）上限，如 20.0 表示 PE ≤ 20
        pb_max: PB 上限，如 3.0
        total_mv_min: 总市值下限（万元），如 1000000（即 100亿）
        total_mv_max: 总市值上限（万元）
        dv_ratio_min: 股息率下限（%），如 3.0
        page: 页码
        page_size: 每页条数，默认 200
    """
    data = await _get("/stocks/daily-basic/snapshot", {
        "trade_date": trade_date,
        "pe_ttm_max": pe_ttm_max,
        "pb_max": pb_max,
        "total_mv_min": total_mv_min,
        "total_mv_max": total_mv_max,
        "dv_ratio_min": dv_ratio_min,
        "page": page,
        "page_size": page_size,
    })
    return _fmt(data)


@mcp.tool()
async def get_stock_indicators(
    ts_code: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    indicators: Optional[str] = None,
) -> str:
    """获取股票技术指标（MA、MACD、RSI、KDJ、布林带等）。
    可用指标：ma5/ma10/ma20/ma30/ma60/ma120/ma200/ma250/ma500、macd/macd_dif/macd_dea、
    rsi14、kdj_k/kdj_d/kdj_j、boll/boll_ub/boll_lb。

    Args:
        ts_code: 股票代码，如 000001.SZ
        start_date: 开始日期，格式 YYYYMMDD
        end_date: 结束日期，格式 YYYYMMDD
        indicators: 指定指标字段，逗号分隔，如 "ma5,ma20,macd,rsi14"；不填则返回所有指标
    """
    data = await _get(f"/stocks/{ts_code}/indicators", {
        "start_date": start_date,
        "end_date": end_date,
        "indicators": indicators,
        "format": "records",
    })
    return _fmt(data)


@mcp.tool()
async def get_stock_candles(ts_code: str, start_date: Optional[str] = None, end_date: Optional[str] = None) -> str:
    """获取股票 K 线数据（包含前复权价格，用于图表展示）。

    Args:
        ts_code: 股票代码，如 600519.SH
        start_date: 开始日期，格式 YYYYMMDD
        end_date: 结束日期，格式 YYYYMMDD
    """
    data = await _get(f"/stocks/{ts_code}/candles", {
        "start_date": start_date,
        "end_date": end_date,
    })
    return _fmt(data)


# ── 3. 行业与板块 ─────────────────────────────────────────────────────────────

@mcp.tool()
async def get_shenwan_industry_tree(level: Optional[int] = None) -> str:
    """获取申万行业分类体系（三级行业树形结构）。
    申万行业是 A 股最主流的行业分类标准，分一级（31个）/二级/三级。

    Args:
        level: 行业级别，1（一级）/2（二级）/3（三级），不填则返回完整树
    """
    data = await _get("/industry/shenwan/tree", {"level": level})
    return _fmt(data)


@mcp.tool()
async def get_shenwan_members(
    industry_code: Optional[str] = None,
    ts_code: Optional[str] = None,
    page: int = 1,
    page_size: int = 200,
) -> str:
    """获取申万行业成员股票列表，或反查某只股票所属行业。

    Args:
        industry_code: 行业代码，如 "801010"（农林牧渔一级）或 index_code 如 "801011.SI"
        ts_code: 反查某只股票属于哪个申万行业
        page: 页码
        page_size: 每页条数，默认 200
    """
    data = await _get("/industry/shenwan/members", {
        "industry_code": industry_code,
        "ts_code": ts_code,
        "page": page,
        "page_size": page_size,
    })
    return _fmt(data)


@mcp.tool()
async def get_sector_ranking(
    trade_date: Optional[str] = None,
    period: str = "1d",
) -> str:
    """获取申万一级行业涨跌幅排名（板块轮动分析核心数据）。

    Args:
        trade_date: 截止交易日，格式 YYYYMMDD，不填则取最近交易日
        period: 统计周期，1d/5d/10d/20d/60d，默认 1d（今日涨幅排名）
    """
    data = await _get("/industry/shenwan/daily/ranking", {
        "trade_date": trade_date,
        "period": period,
    })
    return _fmt(data)


@mcp.tool()
async def get_citic_industry_tree(level: Optional[int] = None) -> str:
    """获取中信行业分类体系（与申万并列的另一主流行业分类）。

    Args:
        level: 行业级别 1/2/3，不填则返回全部层级
    """
    data = await _get("/industry/citic/tree", {"level": level})
    return _fmt(data)


@mcp.tool()
async def get_citic_members(
    industry_code: Optional[str] = None,
    ts_code: Optional[str] = None,
    page: int = 1,
    page_size: int = 200,
) -> str:
    """获取中信行业成员股票列表，或反查某只股票所属行业。

    Args:
        industry_code: 行业代码
        ts_code: 反查某只股票属于哪个中信行业
        page: 页码
        page_size: 每页条数，默认 200
    """
    data = await _get("/industry/citic/members", {
        "industry_code": industry_code,
        "ts_code": ts_code,
        "page": page,
        "page_size": page_size,
    })
    return _fmt(data)


# ── 4. 财务数据 ───────────────────────────────────────────────────────────────

@mcp.tool()
async def get_stock_financials(
    ts_code: str,
    period_type: str = "quarterly",
    limit: int = 8,
) -> str:
    """获取股票核心财务指标（ROE、净利润率、营收增速、资产负债率、FCF 等）。

    Args:
        ts_code: 股票代码，如 600519.SH
        period_type: 报告期类型，quarterly（季报，默认）或 annual（年报）
        limit: 返回期数，默认 8 期（约2年季报）
    """
    data = await _get(f"/stocks/{ts_code}/financials/indicators", {
        "period_type": period_type,
        "limit": limit,
    })
    return _fmt(data)


@mcp.tool()
async def screen_financials(
    roe_min: Optional[float] = None,
    revenue_yoy_min: Optional[float] = None,
    n_income_yoy_min: Optional[float] = None,
    debt_to_assets_max: Optional[float] = None,
    netprofit_margin_min: Optional[float] = None,
    fcf_positive: Optional[bool] = None,
    page: int = 1,
    page_size: int = 200,
) -> str:
    """按财务指标筛选全市场股票（ROE、增速、负债率、盈利能力组合筛选）。

    Args:
        roe_min: ROE 下限（%），如 15.0 表示 ROE ≥ 15%
        revenue_yoy_min: 营收同比增速下限（%），如 10.0
        n_income_yoy_min: 净利润同比增速下限（%）
        debt_to_assets_max: 资产负债率上限（%），如 60.0
        netprofit_margin_min: 净利润率下限（%）
        fcf_positive: True 要求自由现金流为正，False 反之，None 不限
        page: 页码
        page_size: 每页条数，默认 200
    """
    data = await _get("/stocks/financials/indicators/screen", {
        "roe_min": roe_min,
        "revenue_yoy_min": revenue_yoy_min,
        "n_income_yoy_min": n_income_yoy_min,
        "debt_to_assets_max": debt_to_assets_max,
        "netprofit_margin_min": netprofit_margin_min,
        "fcf_positive": fcf_positive,
        "page": page,
        "page_size": page_size,
    })
    return _fmt(data)


@mcp.tool()
async def get_stock_dividends_summary(ts_code: str) -> str:
    """获取股票股息摘要（连续分红年数、近5年平均股息率、现金分红总额、最新股息率）。

    Args:
        ts_code: 股票代码，如 600519.SH
    """
    data = await _get(f"/stocks/{ts_code}/dividends/summary")
    return _fmt(data)


@mcp.tool()
async def screen_dividends(
    dv_ratio_min: Optional[float] = None,
    consecutive_years_min: Optional[int] = None,
    payout_ratio_max: Optional[float] = None,
    page: int = 1,
    page_size: int = 200,
) -> str:
    """按股息指标筛选高分红股票（适合寻找红利策略标的）。

    Args:
        dv_ratio_min: 股息率下限（%），如 3.0 表示 ≥ 3%
        consecutive_years_min: 连续分红年数下限，如 5
        payout_ratio_max: 分红比例上限（%），如 80.0
        page: 页码
        page_size: 每页条数
    """
    data = await _get("/stocks/dividends/screen", {
        "dv_ratio_min": dv_ratio_min,
        "consecutive_years_min": consecutive_years_min,
        "payout_ratio_max": payout_ratio_max,
        "page": page,
        "page_size": page_size,
    })
    return _fmt(data)


# ── 5. 交易信号 ───────────────────────────────────────────────────────────────

@mcp.tool()
async def get_signal_dates() -> str:
    """获取系统中所有可用的交易信号日期列表（用于了解信号覆盖范围）。"""
    data = await _get("/daily-signals/dates")
    return _fmt(data)


@mcp.tool()
async def get_daily_signals(
    trade_date: Optional[str] = None,
    ts_code: Optional[str] = None,
    strategy: Optional[str] = None,
    signal: Optional[str] = None,
) -> str:
    """查询某交易日的选股信号（BUY/SELL/HOLD），包含股票名称、行业、当日及次日涨跌幅等。
    这是 Freedom 核心产出，适合分析策略有效性和选股结果。

    Args:
        trade_date: 交易日期，格式 YYYYMMDD，不填则取最新信号日
        ts_code: 指定股票代码，如 000001.SZ
        strategy: 策略名称过滤，不填则返回所有策略的信号
        signal: 信号类型过滤，BUY/SELL/HOLD
    """
    data = await _get("/daily-signals", {
        "trading_date": trade_date,
        "stock_code": ts_code,
        "strategy": strategy,
        "signal": signal,
    })
    return _fmt(data)


@mcp.tool()
async def get_daily_stock_signals_overview(
    trade_date: Optional[str] = None,
    top_n: int = 20,
) -> str:
    """获取每日股票信号总览（Top N 强信号股票，综合评分排序）。
    适合快速了解当天哪些股票信号最强，作为关注列表的参考。

    Args:
        trade_date: 交易日期，格式 YYYYMMDD，不填则取最新信号日
        top_n: 返回前 N 只股票，默认 20
    """
    data = await _get("/daily-stock-signals/overview", {
        "trade_date": trade_date,
        "top_n": top_n,
    })
    return _fmt(data)


@mcp.tool()
async def list_strategies() -> str:
    """获取系统中所有可用的交易策略列表。"""
    data = await _get("/strategies")
    return _fmt(data)


@mcp.tool()
async def get_strategy_signals(
    strategy_name: str,
    trade_date: Optional[str] = None,
    top_n: int = 20,
) -> str:
    """获取指定策略的信号详情。

    Args:
        strategy_name: 策略名称
        trade_date: 交易日期，格式 YYYYMMDD，不填则取最新信号日
        top_n: 返回前 N 条信号，默认 20
    """
    data = await _get("/strategy-signals", {
        "strategy_name": strategy_name,
        "trade_date": trade_date,
        "top_n": top_n,
    })
    return _fmt(data)


# ── 6. 回测 ───────────────────────────────────────────────────────────────

@mcp.tool()
async def list_backtests() -> str:
    """获取所有回测任务列表。"""
    data = await _get("/backtests")
    return _fmt(data)


@mcp.tool()
async def get_backtest(backtest_id: str) -> str:
    """获取指定回测任务的详情和结果。

    Args:
        backtest_id: 回测任务 ID
    """
    data = await _get(f"/backtests/{backtest_id}")
    return _fmt(data)


@mcp.tool()
async def create_backtest(
    strategy_name: str,
    ts_code: str,
    start_date: str,
    end_date: str,
    initial_capital: float = 100000.0,
) -> str:
    """创建一个新的回测任务。

    Args:
        strategy_name: 策略名称
        ts_code: 股票代码，如 600519.SH
        start_date: 回测开始日期，格式 YYYYMMDD
        end_date: 回测结束日期，格式 YYYYMMDD
        initial_capital: 初始资金，默认 100000
    """
    data = await _post("/backtests", {
        "strategy_name": strategy_name,
        "ts_code": ts_code,
        "start_date": start_date,
        "end_date": end_date,
        "initial_capital": initial_capital,
    })
    return _fmt(data)


# ── 7. 综合研究 ───────────────────────────────────────────────────────────────

@mcp.tool()
async def get_stock_overview(ts_code: str) -> str:
    """获取股票综合研究概览（基本面、估值、技术面、分红、持仓、事件等全面汇总）。
    这是深度研究单只股票的最佳入口，一次调用获取全面信息。

    Args:
        ts_code: 股票代码，如 600519.SH
    """
    data = await _get(f"/research/stocks/{ts_code}/overview")
    return _fmt(data)


@mcp.tool()
async def get_stock_chips(ts_code: str) -> str:
    """获取股票筹码分布分析（成本分布、获利盘比例、套牢盘分布、主力成本区间）。

    Args:
        ts_code: 股票代码，如 000858.SZ
    """
    data = await _get(f"/research/stocks/{ts_code}/chips")
    return _fmt(data)


@mcp.tool()
async def get_stock_moneyflow(ts_code: str) -> str:
    """获取股票资金流向分析（主力/超大单/大单/中单/散户净流入流出趋势）。

    Args:
        ts_code: 股票代码，如 000858.SZ
    """
    data = await _get(f"/research/stocks/{ts_code}/flows")
    return _fmt(data)


@mcp.tool()
async def get_stock_events(ts_code: str) -> str:
    """获取股票重大事件记录（回购、股权变动、M&A等公司事件）。

    Args:
        ts_code: 股票代码，如 000001.SZ
    """
    data = await _get(f"/research/stocks/{ts_code}/events")
    return _fmt(data)


@mcp.tool()
async def get_stock_insider_trades(
    ts_code: str,
    trade_type: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> str:
    """获取股票大股东/高管增减持记录（内部人交易信号）。

    Args:
        ts_code: 股票代码，如 000001.SZ
        trade_type: 交易类型，IN（增持）或 DE（减持），不填则返回全部
        start_date: 开始日期，格式 YYYYMMDD
        end_date: 结束日期，格式 YYYYMMDD
    """
    data = await _get(f"/stocks/{ts_code}/insider-trades", {
        "trade_type": trade_type,
        "start_date": start_date,
        "end_date": end_date,
    })
    return _fmt(data)


@mcp.tool()
async def get_market_sectors_research() -> str:
    """获取市场行业板块综合研究数据（各行业估值中位数、资金流向、近期涨跌幅汇总）。
    适合做板块轮动分析和行业配置决策。
    """
    data = await _get("/research/market/sectors")
    return _fmt(data)


@mcp.tool()
async def get_market_hsgt_flow() -> str:
    """获取沪深港通（北向资金）资金流向研究数据（外资净流入趋势、持仓变化）。"""
    data = await _get("/research/market/hsgt")
    return _fmt(data)


# ── 8. 市场数据 ───────────────────────────────────────────────────────────────

@mcp.tool()
async def get_market_index_list() -> str:
    """获取所有市场指数列表。"""
    data = await _get("/market-index")
    return _fmt(data)


@mcp.tool()
async def get_market_index_data(
    index_code: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> str:
    """获取指定市场指数的历史数据。

    Args:
        index_code: 指数代码，如 "000001.SH"
        start_date: 开始日期，格式 YYYYMMDD
        end_date: 结束日期，格式 YYYYMMDD
    """
    data = await _get(f"/market-index/{index_code}", {
        "start_date": start_date,
        "end_date": end_date,
    })
    return _fmt(data)


@mcp.tool()
async def get_market_regime() -> str:
    """获取当前市场状态分析（趋势/震荡/下跌等市场阶段判断）。"""
    data = await _get("/market-regime")
    return _fmt(data)


@mcp.tool()
async def get_market_data_overview() -> str:
    """获取市场数据总览（全市场概况、涨跌停统计、成交量等）。"""
    data = await _get("/market-data/overview")
    return _fmt(data)


# ── 9. 宏观数据 ───────────────────────────────────────────────────────────────

@mcp.tool()
async def get_macro_lpr(limit: int = 36) -> str:
    """获取贷款市场报价利率（LPR）历史数据（1年期和5年期，反映货币政策取向）。

    Args:
        limit: 返回最近 N 期，默认 36 期（约3年月度数据）
    """
    data = await _get("/macro/lpr", {"limit": limit})
    return _fmt(data)


@mcp.tool()
async def get_macro_money_supply(limit: int = 36) -> str:
    """获取货币供应量（M0/M1/M2）历史数据及同比增速（判断流动性松紧的关键指标）。

    Args:
        limit: 返回最近 N 期，默认 36 期（约3年月度数据）
    """
    data = await _get("/macro/money-supply", {"limit": limit})
    return _fmt(data)


@mcp.tool()
async def get_macro_cpi_ppi(limit: int = 36) -> str:
    """获取 CPI（居民消费价格）和 PPI（工业品出厂价格）历史数据（通胀预期核心指标）。

    Args:
        limit: 返回最近 N 期，默认 36 期（约3年月度数据）
    """
    data = await _get("/macro/cpi-ppi", {"limit": limit})
    return _fmt(data)


@mcp.tool()
async def get_macro_pmi(limit: int = 36) -> str:
    """获取 PMI（制造业采购经理指数）历史数据（判断经济扩张/收缩的领先指标）。

    Args:
        limit: 返回最近 N 期，默认 36 期（约3年月度数据）
    """
    data = await _get("/macro/pmi", {"limit": limit})
    return _fmt(data)


# ── 10. 数据同步与审计 ─────────────────────────────────────────────────────────

@mcp.tool()
async def trigger_data_sync(sync_type: str = "daily") -> str:
    """触发数据同步任务。

    Args:
        sync_type: 同步类型，daily（日度）/full（全量）
    """
    data = await _post("/data-sync", {"sync_type": sync_type})
    return _fmt(data)


@mcp.tool()
async def get_internal_audits() -> str:
    """获取内部审计记录列表。"""
    data = await _get("/internal-audits")
    return _fmt(data)


# ── 11. Agent 专用接口 ────────────────────────────────────────────────────────

@mcp.tool()
async def agent_get_stock_summary(ts_code: str) -> str:
    """Agent 专用：获取股票综合摘要（为 AI agent 优化的精简格式）。

    Args:
        ts_code: 股票代码，如 600519.SH
    """
    data = await _get(f"/agent/freedom/stocks/{ts_code}/summary")
    return _fmt(data)


@mcp.tool()
async def agent_get_daily_report(trade_date: Optional[str] = None) -> str:
    """Agent 专用：获取每日市场报告（为 AI agent 优化的精简格式）。

    Args:
        trade_date: 交易日期，格式 YYYYMMDD，不填则取最新交易日
    """
    data = await _get("/agent/freedom/daily-report", {"trade_date": trade_date})
    return _fmt(data)


@mcp.tool()
async def agent_search_stocks(
    query: str,
    filters: Optional[str] = None,
    limit: int = 20,
) -> str:
    """Agent 专用：智能搜索股票（支持自然语言查询）。

    Args:
        query: 搜索查询，如 "高股息率低估值的银行股"
        filters: 额外过滤条件 JSON 字符串
        limit: 返回数量，默认 20
    """
    data = await _get("/agent/freedom/stocks/search", {
        "query": query,
        "filters": filters,
        "limit": limit,
    })
    return _fmt(data)


@mcp.tool()
async def agent_get_recommended_stocks(strategy: Optional[str] = None, limit: int = 10) -> str:
    """Agent 专用：获取推荐股票列表。

    Args:
        strategy: 策略名称，不填则使用默认策略
        limit: 返回数量，默认 10
    """
    data = await _get("/agent/freedom/stocks/recommended", {
        "strategy": strategy,
        "limit": limit,
    })
    return _fmt(data)


@mcp.tool()
async def agent_get_portfolio_analysis(ts_codes: str) -> str:
    """Agent 专用：获取投资组合分析。

    Args:
        ts_codes: 股票代码列表，逗号分隔，如 "600519.SH,000858.SZ"
    """
    data = await _get("/agent/freedom/portfolio/analysis", {"ts_codes": ts_codes})
    return _fmt(data)


if __name__ == "__main__":
    mcp.run()
