from __future__ import annotations

from pathlib import Path

from app.audit.models import DatasetConfig
from app.core.config import settings
from app.data.duckdb_store import get_connection
from app.data.mongo import get_collection


def _normalize_date(value: object) -> str:
    return str(value or "").replace("-", "").strip()


def _date_filter_sql(field_name: str, start_date: str | None, end_date: str | None) -> tuple[str, list[str]]:
    normalized = f"REPLACE(CAST({field_name} AS VARCHAR), '-', '')"
    clauses: list[str] = []
    params: list[str] = []
    if start_date:
        clauses.append(f"{normalized} >= ?")
        params.append(start_date)
    if end_date:
        clauses.append(f"{normalized} <= ?")
        params.append(end_date)
    if not clauses:
        return "", params
    return f"WHERE {' AND '.join(clauses)}", params


def _excluded_ts_code_filter_sql(config: DatasetConfig) -> tuple[str, list[str]]:
    if not config.coverage_key:
        return "", []
    clauses: list[str] = []
    params: list[str] = []
    normalized_field = f"CAST({config.coverage_key} AS VARCHAR)"
    for suffix in config.baseline_excluded_ts_code_suffixes:
        clauses.append(f"{normalized_field} NOT LIKE ?")
        params.append(f"%{suffix}")
    if config.baseline_excluded_ts_codes:
        placeholders = ", ".join("?" for _ in config.baseline_excluded_ts_codes)
        clauses.append(f"{normalized_field} NOT IN ({placeholders})")
        params.extend(config.baseline_excluded_ts_codes)
    if not clauses:
        return "", []
    return " AND ".join(clauses), params


def _parquet_glob(location: str) -> str:
    root = settings.data_dir / location
    return str(root / "ts_code=*/year=*/part-*.parquet")


def load_open_trade_dates(start_date: str | None = None, end_date: str | None = None, exchange: str = "SSE") -> list[str]:
    query: dict[str, object] = {"exchange": exchange, "is_open": {"$in": ["1", 1]}}
    date_query: dict[str, str] = {}
    if start_date:
        date_query["$gte"] = start_date
    if end_date:
        date_query["$lte"] = end_date
    if date_query:
        query["cal_date"] = date_query
    cursor = get_collection("trade_calendar").find(query, {"_id": 0, "cal_date": 1}).sort("cal_date", 1)
    return [_normalize_date(item.get("cal_date")) for item in cursor if item.get("cal_date")]


def load_counts_by_date(
    config: DatasetConfig,
    *,
    count_mode: str = "auto",
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, int]:
    if count_mode == "auto":
        count_mode = "distinct" if config.audit_mode == "date_and_coverage" else "rows"
    if config.storage_type == "parquet":
        return _load_parquet_counts_by_date(config, count_mode=count_mode, start_date=start_date, end_date=end_date)
    if config.storage_type == "duckdb":
        return _load_duckdb_counts_by_date(config, count_mode=count_mode, start_date=start_date, end_date=end_date)
    if config.storage_type == "mongo":
        return _load_mongo_counts_by_date(config, count_mode=count_mode, start_date=start_date, end_date=end_date)
    raise ValueError(f"unsupported storage_type: {config.storage_type}")


def _load_parquet_counts_by_date(
    config: DatasetConfig,
    *,
    count_mode: str,
    start_date: str | None,
    end_date: str | None,
) -> dict[str, int]:
    root = settings.data_dir / config.location
    if not root.exists():
        return {}
    glob = _parquet_glob(config.location)
    date_expr = f"REPLACE(CAST({config.date_field} AS VARCHAR), '-', '')"
    where_sql, params = _date_filter_sql(config.date_field, start_date, end_date)
    excluded_sql, excluded_params = _excluded_ts_code_filter_sql(config)
    if excluded_sql:
        connector = " AND " if where_sql else "WHERE "
        where_sql = f"{where_sql} {connector}{excluded_sql}".strip()
        params = [*params, *excluded_params]
    value_expr = "COUNT(*)"
    if count_mode == "distinct":
        if not config.coverage_key:
            raise ValueError(f"coverage_key missing for dataset {config.name}")
        value_expr = f"COUNT(DISTINCT {config.coverage_key})"
    query = (
        f"SELECT {date_expr} AS trade_date, {value_expr} AS value "
        f"FROM read_parquet(?, union_by_name=true) {where_sql} "
        "GROUP BY 1 ORDER BY 1"
    )
    with get_connection(read_only=True) as con:
        rows = con.execute(query, [glob, *params]).fetchall()
    return {str(trade_date): int(value) for trade_date, value in rows if trade_date}


def _load_duckdb_counts_by_date(
    config: DatasetConfig,
    *,
    count_mode: str,
    start_date: str | None,
    end_date: str | None,
) -> dict[str, int]:
    date_expr = f"REPLACE(CAST({config.date_field} AS VARCHAR), '-', '')"
    where_sql, params = _date_filter_sql(config.date_field, start_date, end_date)
    excluded_sql, excluded_params = _excluded_ts_code_filter_sql(config)
    if excluded_sql:
        connector = " AND " if where_sql else "WHERE "
        where_sql = f"{where_sql} {connector}{excluded_sql}".strip()
        params = [*params, *excluded_params]
    value_expr = "COUNT(*)"
    if count_mode == "distinct":
        if not config.coverage_key:
            raise ValueError(f"coverage_key missing for dataset {config.name}")
        value_expr = f"COUNT(DISTINCT {config.coverage_key})"
    query = (
        f"SELECT {date_expr} AS trade_date, {value_expr} AS value "
        f"FROM {config.location} {where_sql} "
        "GROUP BY 1 ORDER BY 1"
    )
    with get_connection(read_only=True) as con:
        rows = con.execute(query, params).fetchall()
    return {str(trade_date): int(value) for trade_date, value in rows if trade_date}


def _load_mongo_counts_by_date(
    config: DatasetConfig,
    *,
    count_mode: str,
    start_date: str | None,
    end_date: str | None,
) -> dict[str, int]:
    collection = get_collection(config.location)
    match: dict[str, object] = {config.date_field: {"$exists": True, "$ne": None}}
    date_query: dict[str, str] = {}
    if start_date:
        date_query["$gte"] = start_date
    if end_date:
        date_query["$lte"] = end_date
    if date_query:
        match[config.date_field] = {"$exists": True, "$ne": None, **date_query}
    if config.coverage_key and (config.baseline_excluded_ts_code_suffixes or config.baseline_excluded_ts_codes):
        code_filters: list[dict[str, object]] = []
        for suffix in config.baseline_excluded_ts_code_suffixes:
            code_filters.append({config.coverage_key: {"$not": {"$regex": f"{suffix.replace('.', '\\.')}$"}}})
        if config.baseline_excluded_ts_codes:
            code_filters.append({config.coverage_key: {"$nin": list(config.baseline_excluded_ts_codes)}})
        if code_filters:
            match["$and"] = code_filters

    if count_mode == "distinct":
        if not config.coverage_key:
            raise ValueError(f"coverage_key missing for dataset {config.name}")
        pipeline = [
            {"$match": match},
            {"$group": {"_id": {"trade_date": f"${config.date_field}", "value": f"${config.coverage_key}"}}},
            {"$group": {"_id": "$_id.trade_date", "value": {"$sum": 1}}},
            {"$sort": {"_id": 1}},
        ]
    else:
        pipeline = [
            {"$match": match},
            {"$group": {"_id": f"${config.date_field}", "value": {"$sum": 1}}},
            {"$sort": {"_id": 1}},
        ]

    rows = collection.aggregate(pipeline, allowDiskUse=True)
    return {_normalize_date(item.get("_id")): int(item.get("value") or 0) for item in rows if item.get("_id")}
