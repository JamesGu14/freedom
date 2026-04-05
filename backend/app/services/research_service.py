from __future__ import annotations

import datetime as dt
from collections.abc import Iterable
from typing import Any

import duckdb
import pandas as pd
from pymongo import DESCENDING

from app.api.stock_code import resolve_ts_code_input
from app.core.config import settings
from app.data.duckdb_store import get_connection
from app.data.mongo import get_collection
from app.data.mongo_index_data import DEFAULT_INDEX_DAILY_WHITELIST
from app.data.mongo_stock import get_stock_basic_by_code


def _normalize_ts_code(ts_code: str) -> str:
    return resolve_ts_code_input(ts_code, strict=False)


def _normalize_date(value: str | None) -> str | None:
    text = str(value or "").strip().replace("-", "")
    if not text:
        return None
    if len(text) != 8 or not text.isdigit():
        raise ValueError(f"invalid date: {value}")
    return text


def _today_ymd() -> str:
    return dt.datetime.now().strftime("%Y%m%d")


def _default_start_date(days: int = 365) -> str:
    return (dt.datetime.now() - dt.timedelta(days=days)).strftime("%Y%m%d")


def _to_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    if df.empty:
        return []
    normalized = df.where(pd.notna(df), None)
    return normalized.to_dict(orient="records")


def _safe_fetch_df(query: str, params: Iterable[Any] | None = None) -> pd.DataFrame:
    with get_connection(read_only=True) as con:
        try:
            if params is None:
                return con.execute(query).fetchdf()
            return con.execute(query, list(params)).fetchdf()
        except (duckdb.CatalogException, duckdb.IOException):
            return pd.DataFrame()


def _query_duckdb_table(
    table: str,
    *,
    ts_code: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    date_field: str = "trade_date",
    order_fields: list[str] | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    query = [f"SELECT * FROM {table} WHERE 1=1"]
    params: list[Any] = []
    if ts_code:
        query.append("AND ts_code = ?")
        params.append(ts_code)
    if start_date:
        query.append(f"AND {date_field} >= ?")
        params.append(start_date)
    if end_date:
        query.append(f"AND {date_field} <= ?")
        params.append(end_date)
    if order_fields:
        query.append("ORDER BY " + ", ".join(order_fields))
    if limit is not None:
        query.append("LIMIT ?")
        params.append(int(limit))
    return _to_records(_safe_fetch_df(" ".join(query), params))


def _query_partitioned_parquet(
    dataset: str,
    *,
    ts_code: str,
    base_dir: str = "features",
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    parquet_root = settings.data_dir / base_dir / dataset / f"ts_code={ts_code}"
    if not parquet_root.exists():
        return []
    part_glob = str(parquet_root / "year=*/part-*.parquet")
    query = [
        "SELECT * FROM read_parquet(?, hive_partitioning=1, union_by_name=true)",
        "WHERE ts_code = ?",
    ]
    params: list[Any] = [part_glob, ts_code]
    if start_date:
        query.append("AND trade_date >= ?")
        params.append(start_date)
    if end_date:
        query.append("AND trade_date <= ?")
        params.append(end_date)
    query.append("ORDER BY trade_date DESC")
    if limit is not None:
        query.append("LIMIT ?")
        params.append(int(limit))
    return _to_records(_safe_fetch_df(" ".join(query), params))


def _query_mongo(
    collection_name: str,
    *,
    query: dict[str, Any],
    projection: dict[str, int] | None = None,
    sort: list[tuple[str, int]] | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    cursor = get_collection(collection_name).find(query, projection or {"_id": 0})
    if sort:
        cursor = cursor.sort(sort)
    if limit is not None:
        cursor = cursor.limit(max(int(limit), 0))
    return list(cursor)


def _get_stock_basic(ts_code: str) -> dict[str, Any] | None:
    return get_stock_basic_by_code(ts_code)


def _get_latest_daily(ts_code: str) -> dict[str, Any] | None:
    rows = _query_partitioned_parquet("daily", ts_code=ts_code, base_dir="raw", limit=1)
    return rows[0] if rows else None


def _get_latest_daily_basic(ts_code: str) -> dict[str, Any] | None:
    rows = _query_partitioned_parquet("daily_basic", ts_code=ts_code, base_dir="raw", limit=1)
    return rows[0] if rows else None


def _get_latest_indicator(ts_code: str) -> dict[str, Any] | None:
    rows = _query_partitioned_parquet("indicators", ts_code=ts_code, limit=1)
    return rows[0] if rows else None


def _get_latest_financial_indicator(ts_code: str) -> dict[str, Any] | None:
    rows = _query_duckdb_table(
        "fina_indicator",
        ts_code=ts_code,
        date_field="end_date",
        order_fields=["end_date DESC", "ann_date DESC"],
        limit=1,
    )
    return rows[0] if rows else None


def _get_dividend_rows(ts_code: str, limit: int = 100) -> list[dict[str, Any]]:
    return _query_mongo(
        "dividend_history",
        query={"ts_code": ts_code},
        sort=[("end_date", DESCENDING), ("ann_date", DESCENDING)],
        limit=limit,
    )


def _sum_ratio(items: list[dict[str, Any]]) -> float | None:
    values = [float(item.get("hold_ratio")) for item in items if isinstance(item.get("hold_ratio"), (int, float))]
    if not values:
        return None
    return round(sum(values), 4)


def _get_dividend_summary(ts_code: str) -> dict[str, Any]:
    items = _get_dividend_rows(ts_code, limit=200)
    if not items:
        return {
            "latest_ann_date": None,
            "latest_cash_div": None,
            "latest_stk_div": None,
            "dividend_count": 0,
            "consecutive_years": 0,
        }
    latest = items[0]
    years = []
    for item in items:
        end_date = str(item.get("end_date") or "")
        if len(end_date) >= 4 and end_date[:4].isdigit():
            years.append(int(end_date[:4]))
    years = sorted(set(years), reverse=True)
    consecutive = 0
    if years:
        expected = years[0]
        for year in years:
            if year == expected:
                consecutive += 1
                expected -= 1
            else:
                break
    return {
        "latest_ann_date": latest.get("ann_date"),
        "latest_cash_div": latest.get("cash_div"),
        "latest_stk_div": latest.get("stk_div"),
        "dividend_count": len(items),
        "consecutive_years": consecutive,
    }


def _get_holdernumber_rows(ts_code: str, limit: int = 24) -> list[dict[str, Any]]:
    return _query_duckdb_table(
        "stk_holdernumber",
        ts_code=ts_code,
        date_field="ann_date",
        order_fields=["ann_date DESC", "end_date DESC"],
        limit=limit,
    )


def _get_top10_holder_rows(collection_name: str, ts_code: str, limit: int = 50) -> list[dict[str, Any]]:
    return _query_mongo(
        collection_name,
        query={"ts_code": ts_code},
        sort=[("end_date", DESCENDING), ("ann_date", DESCENDING)],
        limit=limit,
    )


def _get_holder_summary(ts_code: str) -> dict[str, Any]:
    holder_number = _get_holdernumber_rows(ts_code, limit=24)
    top10_holders = _get_top10_holder_rows("top10_holders", ts_code, limit=20)
    top10_floatholders = _get_top10_holder_rows("top10_floatholders", ts_code, limit=20)
    latest_holder_num = holder_number[0].get("holder_num") if holder_number else None
    previous_holder_num = holder_number[1].get("holder_num") if len(holder_number) > 1 else None
    holder_num_change = None
    if isinstance(latest_holder_num, (int, float)) and isinstance(previous_holder_num, (int, float)):
        holder_num_change = latest_holder_num - previous_holder_num
    latest_holder_end_date = top10_holders[0].get("end_date") if top10_holders else None
    latest_float_end_date = top10_floatholders[0].get("end_date") if top10_floatholders else None
    latest_top10 = [item for item in top10_holders if item.get("end_date") == latest_holder_end_date] if latest_holder_end_date else []
    latest_top10_float = [item for item in top10_floatholders if item.get("end_date") == latest_float_end_date] if latest_float_end_date else []
    return {
        "latest_holder_num": latest_holder_num,
        "holder_num_change": holder_num_change,
        "top10_holder_ratio": _sum_ratio(latest_top10),
        "top10_float_holder_ratio": _sum_ratio(latest_top10_float),
    }


def _get_moneyflow_dc_rows(ts_code: str, *, start_date: str | None, end_date: str | None, limit: int) -> list[dict[str, Any]]:
    return _query_partitioned_parquet("moneyflow_dc", ts_code=ts_code, start_date=start_date, end_date=end_date, limit=limit)


def _get_margin_detail_rows(ts_code: str, *, start_date: str | None, end_date: str | None, limit: int) -> list[dict[str, Any]]:
    return _query_duckdb_table(
        "margin_detail",
        ts_code=ts_code,
        start_date=start_date,
        end_date=end_date,
        order_fields=["trade_date DESC"],
        limit=limit,
    )


def _get_hk_hold_rows(ts_code: str, *, start_date: str | None, end_date: str | None, limit: int) -> list[dict[str, Any]]:
    query: dict[str, Any] = {"ts_code": ts_code}
    if start_date or end_date:
        query["trade_date"] = {}
        if start_date:
            query["trade_date"]["$gte"] = start_date
        if end_date:
            query["trade_date"]["$lte"] = end_date
    return _query_mongo("hk_hold", query=query, sort=[("trade_date", DESCENDING)], limit=limit)


def _get_ccass_hold_rows(ts_code: str, *, start_date: str | None, end_date: str | None, limit: int) -> list[dict[str, Any]]:
    query: dict[str, Any] = {"ts_code": ts_code}
    if start_date or end_date:
        query["trade_date"] = {}
        if start_date:
            query["trade_date"]["$gte"] = start_date
        if end_date:
            query["trade_date"]["$lte"] = end_date
    return _query_mongo("ccass_hold", query=query, sort=[("trade_date", DESCENDING)], limit=limit)


def _get_flow_summary(ts_code: str) -> dict[str, Any]:
    moneyflow = _get_moneyflow_dc_rows(ts_code, start_date=None, end_date=None, limit=1)
    margin_rows = _get_margin_detail_rows(ts_code, start_date=None, end_date=None, limit=2)
    hk_hold = _get_hk_hold_rows(ts_code, start_date=None, end_date=None, limit=2)
    ccass_hold = _get_ccass_hold_rows(ts_code, start_date=None, end_date=None, limit=2)
    latest_margin = margin_rows[0] if margin_rows else {}
    prev_margin = margin_rows[1] if len(margin_rows) > 1 else {}
    margin_change = None
    if isinstance(latest_margin.get("rzye"), (int, float)) and isinstance(prev_margin.get("rzye"), (int, float)):
        margin_change = float(latest_margin["rzye"]) - float(prev_margin["rzye"])
    return {
        "moneyflow_dc": moneyflow[0].get("net_mf_amount") if moneyflow else None,
        "margin_rzye": latest_margin.get("rzye"),
        "margin_rzye_change": margin_change,
        "hk_hold_vol": hk_hold[0].get("vol") if hk_hold else None,
        "ccass_hold_ratio": ccass_hold[0].get("hold_ratio") if ccass_hold else None,
    }


def _get_suspend_rows(ts_code: str, *, start_date: str | None, end_date: str | None, limit: int) -> list[dict[str, Any]]:
    query: dict[str, Any] = {"ts_code": ts_code}
    if start_date or end_date:
        query["trade_date"] = {}
        if start_date:
            query["trade_date"]["$gte"] = start_date
        if end_date:
            query["trade_date"]["$lte"] = end_date
    return _query_mongo("suspend_d", query=query, sort=[("trade_date", DESCENDING)], limit=limit)


def _get_stk_surv_rows(ts_code: str, *, start_date: str | None, end_date: str | None, limit: int) -> list[dict[str, Any]]:
    query: dict[str, Any] = {"ts_code": ts_code}
    if start_date or end_date:
        query["surv_date"] = {}
        if start_date:
            query["surv_date"]["$gte"] = start_date
        if end_date:
            query["surv_date"]["$lte"] = end_date
    return _query_mongo("stk_surv", query=query, sort=[("surv_date", DESCENDING)], limit=limit)


def _get_event_summary(ts_code: str) -> dict[str, Any]:
    suspend = _get_suspend_rows(ts_code, start_date=None, end_date=None, limit=1)
    surveys = _get_stk_surv_rows(ts_code, start_date=None, end_date=None, limit=1)
    return {
        "latest_suspend_date": suspend[0].get("trade_date") if suspend else None,
        "latest_suspend_type": suspend[0].get("suspend_type") if suspend else None,
        "latest_survey_date": surveys[0].get("surv_date") if surveys else None,
        "latest_survey_org": surveys[0].get("rece_org") if surveys else None,
    }


def _get_chip_perf_rows(ts_code: str, *, start_date: str | None, end_date: str | None, limit: int) -> list[dict[str, Any]]:
    return _query_partitioned_parquet("cyq_perf", ts_code=ts_code, start_date=start_date, end_date=end_date, limit=limit)


def _get_chip_distribution_rows(ts_code: str, *, start_date: str | None, end_date: str | None, limit: int) -> list[dict[str, Any]]:
    return _query_partitioned_parquet("cyq_chips", ts_code=ts_code, start_date=start_date, end_date=end_date, limit=limit)


def _get_chip_summary(ts_code: str) -> dict[str, Any]:
    perf = _get_chip_perf_rows(ts_code, start_date=None, end_date=None, limit=1)
    latest = perf[0] if perf else {}
    return {
        "latest_trade_date": latest.get("trade_date"),
        "latest_win_rate": latest.get("weight_avg") or latest.get("profit_ratio"),
        "latest_cost_focus": latest.get("cost_focus"),
    }


def _get_index_basic_map() -> dict[str, dict[str, Any]]:
    rows = _query_mongo("index_basic", query={}, sort=[("ts_code", 1)], limit=None)
    return {str(item.get("ts_code")): item for item in rows if item.get("ts_code")}


def _get_index_daily_latest_rows(codes: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    collection = get_collection("index_daily")
    for code in codes:
        row = collection.find_one({"ts_code": code}, {"_id": 0}, sort=[("trade_date", DESCENDING)])
        if row:
            rows.append(row)
    return rows


def _get_index_available_dates(limit: int = 60) -> list[str]:
    dates = get_collection("index_daily").distinct("trade_date")
    return sorted([str(item) for item in dates if item], reverse=True)[:limit]


def get_stock_research_overview(ts_code: str) -> dict[str, Any]:
    code = _normalize_ts_code(ts_code)
    return {
        "ts_code": code,
        "basic": _get_stock_basic(code),
        "latest_daily": _get_latest_daily(code),
        "latest_daily_basic": _get_latest_daily_basic(code),
        "latest_indicators": _get_latest_indicator(code),
        "latest_financial_indicator": _get_latest_financial_indicator(code),
        "latest_dividend_summary": _get_dividend_summary(code),
        "latest_holder_summary": _get_holder_summary(code),
        "latest_flow_summary": _get_flow_summary(code),
        "latest_event_summary": _get_event_summary(code),
        "latest_chip_summary": _get_chip_summary(code),
    }


def get_stock_research_financials(ts_code: str, limit: int = 8) -> dict[str, Any]:
    code = _normalize_ts_code(ts_code)
    indicators = _query_duckdb_table("fina_indicator", ts_code=code, date_field="end_date", order_fields=["end_date DESC", "ann_date DESC"], limit=limit)
    income = _query_duckdb_table("income", ts_code=code, date_field="end_date", order_fields=["end_date DESC", "ann_date DESC"], limit=limit)
    balance = _query_duckdb_table("balancesheet", ts_code=code, date_field="end_date", order_fields=["end_date DESC", "ann_date DESC"], limit=limit)
    cashflow = _query_duckdb_table("cashflow", ts_code=code, date_field="end_date", order_fields=["end_date DESC", "ann_date DESC"], limit=limit)
    periods = []
    for row in indicators or income or balance or cashflow:
        end_date = row.get("end_date")
        if end_date and end_date not in periods:
            periods.append(end_date)
    return {
        "ts_code": code,
        "latest_period": periods[0] if periods else None,
        "periods": periods,
        "indicators": indicators,
        "income": income,
        "balance": balance,
        "cashflow": cashflow,
    }


def get_stock_research_dividends(ts_code: str, limit: int = 100) -> dict[str, Any]:
    code = _normalize_ts_code(ts_code)
    items = _get_dividend_rows(code, limit=limit)
    return {
        "ts_code": code,
        "items": items,
        "summary": _get_dividend_summary(code),
    }


def get_stock_research_holders(ts_code: str, limit: int = 24) -> dict[str, Any]:
    code = _normalize_ts_code(ts_code)
    holder_number = _get_holdernumber_rows(code, limit=limit)
    top10_holders = _get_top10_holder_rows("top10_holders", code, limit=limit * 2)
    top10_floatholders = _get_top10_holder_rows("top10_floatholders", code, limit=limit * 2)
    return {
        "ts_code": code,
        "holder_number": holder_number,
        "top10_holders": top10_holders,
        "top10_floatholders": top10_floatholders,
        "summary": _get_holder_summary(code),
    }


def get_stock_research_chips(
    ts_code: str,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 120,
) -> dict[str, Any]:
    code = _normalize_ts_code(ts_code)
    start = _normalize_date(start_date)
    end = _normalize_date(end_date) or _today_ymd()
    return {
        "ts_code": code,
        "cyq_perf": _get_chip_perf_rows(code, start_date=start, end_date=end, limit=limit),
        "cyq_chips": _get_chip_distribution_rows(code, start_date=start, end_date=end, limit=limit),
        "summary": _get_chip_summary(code),
    }


def get_stock_research_flows(
    ts_code: str,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 120,
) -> dict[str, Any]:
    code = _normalize_ts_code(ts_code)
    start = _normalize_date(start_date) or _default_start_date()
    end = _normalize_date(end_date) or _today_ymd()
    return {
        "ts_code": code,
        "moneyflow_dc": _get_moneyflow_dc_rows(code, start_date=start, end_date=end, limit=limit),
        "margin_detail": _get_margin_detail_rows(code, start_date=start, end_date=end, limit=limit),
        "hk_hold": _get_hk_hold_rows(code, start_date=start, end_date=end, limit=limit),
        "ccass_hold": _get_ccass_hold_rows(code, start_date=start, end_date=end, limit=limit),
        "summary": _get_flow_summary(code),
    }


def get_stock_research_events(
    ts_code: str,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 120,
) -> dict[str, Any]:
    code = _normalize_ts_code(ts_code)
    start = _normalize_date(start_date) or _default_start_date()
    end = _normalize_date(end_date) or _today_ymd()
    return {
        "ts_code": code,
        "suspend": _get_suspend_rows(code, start_date=start, end_date=end, limit=limit),
        "institution_surveys": _get_stk_surv_rows(code, start_date=start, end_date=end, limit=limit),
        "summary": _get_event_summary(code),
    }


def get_market_research_indexes() -> dict[str, Any]:
    tracked = list(DEFAULT_INDEX_DAILY_WHITELIST)
    basic_map = _get_index_basic_map()
    latest_rows = _get_index_daily_latest_rows(tracked)
    latest_snapshot = []
    for row in latest_rows:
        code = str(row.get("ts_code") or "")
        item = dict(row)
        item.update({k: v for k, v in (basic_map.get(code) or {}).items() if k not in item})
        latest_snapshot.append(item)
    tracked_indexes = [basic_map.get(code, {"ts_code": code, "name": code}) for code in tracked]
    return {
        "tracked_indexes": tracked_indexes,
        "latest_snapshot": latest_snapshot,
        "available_dates": _get_index_available_dates(limit=60),
    }


def get_market_research_index_detail(ts_code: str, limit: int = 240) -> dict[str, Any]:
    code = _normalize_ts_code(ts_code)
    basic = get_collection("index_basic").find_one({"ts_code": code}, {"_id": 0})
    daily = _query_mongo("index_daily", query={"ts_code": code}, sort=[("trade_date", DESCENDING)], limit=limit)
    dailybasic = _query_mongo("market_index_dailybasic", query={"ts_code": code}, sort=[("trade_date", DESCENDING)], limit=limit)
    factors = _query_mongo("index_factor_pro", query={"ts_code": code}, sort=[("trade_date", DESCENDING)], limit=limit)
    return {
        "ts_code": code,
        "basic": basic,
        "daily": daily,
        "dailybasic": dailybasic,
        "factors": factors,
    }


def get_market_research_sectors(limit: int = 10) -> dict[str, Any]:
    shenwan_latest = get_collection("shenwan_daily").find({}, {"_id": 0, "trade_date": 1}, sort=[("trade_date", DESCENDING)])
    latest_sw = next(iter(shenwan_latest), None)
    latest_sw_date = latest_sw.get("trade_date") if latest_sw else None
    citic_latest = get_collection("citic_daily").find({}, {"_id": 0, "trade_date": 1}, sort=[("trade_date", DESCENDING)])
    latest_ci = next(iter(citic_latest), None)
    latest_ci_date = latest_ci.get("trade_date") if latest_ci else None
    shenwan = _query_mongo(
        "shenwan_daily",
        query={"trade_date": latest_sw_date} if latest_sw_date else {"trade_date": "__none__"},
        sort=[("pct_change", DESCENDING)],
        limit=limit,
    )
    citic = _query_mongo(
        "citic_daily",
        query={"trade_date": latest_ci_date} if latest_ci_date else {"trade_date": "__none__"},
        sort=[("pct_change", DESCENDING)],
        limit=limit,
    )
    return {
        "latest_trade_date": max([d for d in [latest_sw_date, latest_ci_date] if d], default=None),
        "shenwan": shenwan,
        "citic": citic,
    }


def get_market_research_hsgt_flow(
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 120,
) -> dict[str, Any]:
    start = _normalize_date(start_date) or _default_start_date()
    end = _normalize_date(end_date) or _today_ymd()
    query: dict[str, Any] = {}
    query["trade_date"] = {"$gte": start, "$lte": end}
    items = _query_mongo("moneyflow_hsgt", query=query, sort=[("trade_date", DESCENDING)], limit=limit)
    latest = items[0] if items else {}
    return {
        "items": items,
        "summary": {
            "latest_trade_date": latest.get("trade_date"),
            "north_money": latest.get("north_money"),
            "south_money": latest.get("south_money"),
        },
    }
