from __future__ import annotations

import datetime as dt

from pymongo import ASCENDING, DESCENDING, UpdateOne

from app.data.mongo import get_collection

DEFAULT_MARKET_INDEX_CODES = [
    "000001.SH",
    "399001.SZ",
    "399006.SZ",
    "000300.SH",
    "000905.SH",
    "000852.SH",
    "000688.SH",
]

_CHART_FACTOR_FIELDS = {
    "open": "open",
    "high": "high",
    "low": "low",
    "close": "close",
    "vol": "vol",
    "amount": "amount",
    "pct_change": "pct_change",
    "ma_bfq_5": "ma5",
    "ma_bfq_10": "ma10",
    "ma_bfq_20": "ma20",
    "ma_bfq_60": "ma60",
    "macd_dif_bfq": "macd_dif",
    "macd_dea_bfq": "macd_dea",
    "macd_bfq": "macd",
    "kdj_k_bfq": "kdj_k",
    "kdj_d_bfq": "kdj_d",
    "kdj_bfq": "kdj_j",
    "rsi_bfq_6": "rsi6",
    "rsi_bfq_12": "rsi12",
    "rsi_bfq_24": "rsi24",
}

_DAILYBASIC_INDEX_READY = False
_FACTOR_INDEX_READY = False


def _ensure_market_dailybasic_indexes() -> None:
    collection = get_collection("market_index_dailybasic")
    collection.create_index(
        [("ts_code", ASCENDING), ("trade_date", ASCENDING)],
        unique=True,
        name="idx_ts_code_trade_date",
    )
    collection.create_index(
        [("trade_date", DESCENDING)],
        name="idx_trade_date_desc",
    )


def _ensure_index_factor_pro_indexes() -> None:
    collection = get_collection("index_factor_pro")
    collection.create_index(
        [("ts_code", ASCENDING), ("trade_date", ASCENDING)],
        unique=True,
        name="idx_ts_code_trade_date",
    )
    collection.create_index(
        [("source", ASCENDING), ("trade_date", DESCENDING)],
        name="idx_source_trade_date_desc",
    )
    collection.create_index(
        [("trade_date", DESCENDING)],
        name="idx_trade_date_desc",
    )


def get_market_dailybasic_collection():
    global _DAILYBASIC_INDEX_READY
    if not _DAILYBASIC_INDEX_READY:
        _ensure_market_dailybasic_indexes()
        _DAILYBASIC_INDEX_READY = True
    return get_collection("market_index_dailybasic")


def get_index_factor_collection():
    global _FACTOR_INDEX_READY
    if not _FACTOR_INDEX_READY:
        _ensure_index_factor_pro_indexes()
        _FACTOR_INDEX_READY = True
    return get_collection("index_factor_pro")


def upsert_market_index_dailybasic(records: list[dict[str, object]]) -> int:
    if not records:
        return 0

    collection = get_market_dailybasic_collection()
    ops: list[UpdateOne] = []
    now = dt.datetime.now(dt.UTC)
    for record in records:
        record.pop("_id", None)
        record.pop("created_at", None)
        ts_code = record.get("ts_code")
        trade_date = record.get("trade_date")
        if not ts_code or not trade_date:
            continue
        record["updated_at"] = now
        ops.append(
            UpdateOne(
                {"ts_code": ts_code, "trade_date": trade_date},
                {"$set": record, "$setOnInsert": {"created_at": now}},
                upsert=True,
            )
        )

    if not ops:
        return 0

    collection.bulk_write(ops, ordered=False)
    return len(ops)


def upsert_index_factor_pro(records: list[dict[str, object]]) -> int:
    if not records:
        return 0

    collection = get_index_factor_collection()
    ops: list[UpdateOne] = []
    now = dt.datetime.now(dt.UTC)
    for record in records:
        record.pop("_id", None)
        record.pop("created_at", None)
        ts_code = record.get("ts_code")
        trade_date = record.get("trade_date")
        if not ts_code or not trade_date:
            continue
        record["updated_at"] = now
        ops.append(
            UpdateOne(
                {"ts_code": ts_code, "trade_date": trade_date},
                {"$set": record, "$setOnInsert": {"created_at": now}},
                upsert=True,
            )
        )

    if not ops:
        return 0

    collection.bulk_write(ops, ordered=False)
    return len(ops)


def _build_trade_date_query(
    *,
    trade_date: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, object]:
    if trade_date:
        return {"trade_date": trade_date}
    if start_date and end_date:
        return {"trade_date": {"$gte": start_date, "$lte": end_date}}
    if start_date:
        return {"trade_date": {"$gte": start_date}}
    if end_date:
        return {"trade_date": {"$lte": end_date}}
    return {}


def list_market_trade_dates(limit: int = 30) -> list[str]:
    collection = get_market_dailybasic_collection()
    dates = collection.distinct("trade_date")
    dates = sorted((d for d in dates if d), reverse=True)
    return dates[: max(limit, 0)]


def get_market_latest_trade_date() -> str | None:
    dates = list_market_trade_dates(limit=1)
    return dates[0] if dates else None


def get_market_index_overview(
    *,
    trade_date: str | None = None,
    index_codes: list[str] | None = None,
) -> list[dict[str, object]]:
    collection_basic = get_market_dailybasic_collection()
    collection_factor = get_index_factor_collection()

    target_date = trade_date or get_market_latest_trade_date()
    if not target_date:
        return []

    code_filter = index_codes or DEFAULT_MARKET_INDEX_CODES
    query: dict[str, object] = {"trade_date": target_date}
    if code_filter:
        query["ts_code"] = {"$in": code_filter}

    projection_basic = {
        "_id": 0,
        "ts_code": 1,
        "trade_date": 1,
        "total_mv": 1,
        "float_mv": 1,
        "total_share": 1,
        "float_share": 1,
        "free_share": 1,
        "turnover_rate": 1,
        "turnover_rate_f": 1,
        "total_pe": 1,
        "pe": 1,
        "pb": 1,
    }
    basic_rows = list(collection_basic.find(query, projection_basic))

    projection_factor = {
        "_id": 0,
        "ts_code": 1,
        "trade_date": 1,
        "ts_name": 1,
        "pct_change": 1,
        "simple_return": 1,
        "log_return": 1,
        "source": 1,
    }
    factor_query = dict(query)
    factor_query["source"] = "market"
    factor_rows = list(collection_factor.find(factor_query, projection_factor))
    factor_map = {str(item.get("ts_code")): item for item in factor_rows if item.get("ts_code")}

    merged: list[dict[str, object]] = []
    for row in basic_rows:
        ts_code = str(row.get("ts_code"))
        factor = factor_map.get(ts_code, {})
        item = dict(row)
        item["ts_name"] = factor.get("ts_name")
        item["pct_change"] = factor.get("pct_change")
        item["simple_return"] = factor.get("simple_return")
        item["log_return"] = factor.get("log_return")
        item["source"] = "market"
        merged.append(item)

    merged.sort(key=lambda x: str(x.get("ts_code") or ""))
    return merged


def get_market_index_series(
    *,
    ts_code: str,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 240,
) -> list[dict[str, object]]:
    if not ts_code:
        return []

    date_query = _build_trade_date_query(start_date=start_date, end_date=end_date)
    basic_query: dict[str, object] = {"ts_code": ts_code}
    factor_query: dict[str, object] = {"ts_code": ts_code, "source": "market"}
    basic_query.update(date_query)
    factor_query.update(date_query)

    projection_basic = {
        "_id": 0,
        "trade_date": 1,
        "pe": 1,
        "pb": 1,
        "turnover_rate": 1,
        "turnover_rate_f": 1,
        "total_mv": 1,
        "float_mv": 1,
    }
    projection_factor = {
        "_id": 0,
        "trade_date": 1,
        "pct_change": 1,
        "macd_bfq": 1,
        "macd_dif_bfq": 1,
        "macd_dea_bfq": 1,
        "rsi_bfq_6": 1,
        "rsi_bfq_12": 1,
        "rsi_bfq_24": 1,
        "kdj_k_bfq": 1,
        "kdj_d_bfq": 1,
        "kdj_bfq": 1,
    }

    basic_rows = list(
        get_market_dailybasic_collection()
        .find(basic_query, projection_basic)
        .sort([("trade_date", DESCENDING)])
        .limit(max(limit, 0))
    )
    factor_rows = list(
        get_index_factor_collection()
        .find(factor_query, projection_factor)
        .sort([("trade_date", DESCENDING)])
        .limit(max(limit, 0))
    )

    basic_map = {str(item.get("trade_date")): item for item in basic_rows if item.get("trade_date")}
    factor_map = {str(item.get("trade_date")): item for item in factor_rows if item.get("trade_date")}
    all_dates = sorted(set(basic_map.keys()) | set(factor_map.keys()))

    series: list[dict[str, object]] = []
    for trade_date in all_dates:
        basic = basic_map.get(trade_date, {})
        factor = factor_map.get(trade_date, {})
        series.append(
            {
                "ts_code": ts_code,
                "trade_date": trade_date,
                "pct_change": factor.get("pct_change"),
                "pe": basic.get("pe"),
                "pb": basic.get("pb"),
                "turnover_rate": basic.get("turnover_rate"),
                "turnover_rate_f": basic.get("turnover_rate_f"),
                "total_mv": basic.get("total_mv"),
                "float_mv": basic.get("float_mv"),
                "macd": factor.get("macd_bfq"),
                "macd_dif": factor.get("macd_dif_bfq"),
                "macd_dea": factor.get("macd_dea_bfq"),
                "rsi_6": factor.get("rsi_bfq_6"),
                "rsi_12": factor.get("rsi_bfq_12"),
                "rsi_24": factor.get("rsi_bfq_24"),
                "kdj_k": factor.get("kdj_k_bfq"),
                "kdj_d": factor.get("kdj_d_bfq"),
                "kdj_j": factor.get("kdj_bfq"),
            }
        )

    if limit > 0 and len(series) > limit:
        series = series[-limit:]
    return series


def get_market_index_chart(
    *,
    ts_code: str,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 500,
) -> list[dict[str, object]]:
    if not ts_code:
        return []

    date_query = _build_trade_date_query(start_date=start_date, end_date=end_date)
    factor_query: dict[str, object] = {"ts_code": ts_code, "source": "market"}
    basic_query: dict[str, object] = {"ts_code": ts_code}
    factor_query.update(date_query)
    basic_query.update(date_query)

    projection_factor = {"_id": 0, "trade_date": 1}
    for field in _CHART_FACTOR_FIELDS.keys():
        projection_factor[field] = 1
    projection_basic = {
        "_id": 0,
        "trade_date": 1,
        "pe": 1,
        "pb": 1,
    }

    factor_rows = list(
        get_index_factor_collection()
        .find(factor_query, projection_factor)
        .sort([("trade_date", DESCENDING)])
        .limit(max(limit, 0))
    )
    basic_rows = list(
        get_market_dailybasic_collection()
        .find(basic_query, projection_basic)
        .sort([("trade_date", DESCENDING)])
        .limit(max(limit, 0))
    )

    factor_map = {str(item.get("trade_date")): item for item in factor_rows if item.get("trade_date")}
    basic_map = {str(item.get("trade_date")): item for item in basic_rows if item.get("trade_date")}
    all_dates = sorted(set(factor_map.keys()) | set(basic_map.keys()))
    if limit > 0 and len(all_dates) > limit:
        all_dates = all_dates[-limit:]

    items: list[dict[str, object]] = []
    for trade_date in all_dates:
        factor = factor_map.get(trade_date, {})
        basic = basic_map.get(trade_date, {})
        item: dict[str, object] = {
            "ts_code": ts_code,
            "trade_date": trade_date,
            "pe": basic.get("pe"),
            "pb": basic.get("pb"),
        }
        for source_field, target_field in _CHART_FACTOR_FIELDS.items():
            item[target_field] = factor.get(source_field)
        items.append(item)
    return items


def get_market_index_factors(
    *,
    ts_code: str,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 120,
) -> list[dict[str, object]]:
    if not ts_code:
        return []

    query: dict[str, object] = {"ts_code": ts_code, "source": "market"}
    query.update(_build_trade_date_query(start_date=start_date, end_date=end_date))

    rows = list(
        get_index_factor_collection()
        .find(query, {"_id": 0})
        .sort([("trade_date", DESCENDING)])
        .limit(max(limit, 0))
    )
    return rows
