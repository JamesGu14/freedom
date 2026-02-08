from __future__ import annotations

import datetime as dt
from collections import defaultdict

from pymongo import ASCENDING, UpdateOne

from app.data.mongo import get_collection

_INDEX_READY = False


def _ensure_citic_daily_indexes() -> None:
    collection = get_collection("citic_daily")
    collection.create_index(
        [("ts_code", ASCENDING), ("trade_date", ASCENDING)],
        unique=True,
        name="idx_ts_code_trade_date",
    )
    collection.create_index(
        [("trade_date", ASCENDING), ("level", ASCENDING)],
        name="idx_trade_date_level",
    )
    collection.create_index(
        [("level", ASCENDING), ("trade_date", -1), ("rank", ASCENDING)],
        name="idx_level_trade_date_rank",
    )


def get_citic_daily_collection():
    global _INDEX_READY
    if not _INDEX_READY:
        _ensure_citic_daily_indexes()
        _INDEX_READY = True
    return get_collection("citic_daily")


def upsert_citic_daily(records: list[dict[str, object]]) -> int:
    if not records:
        return 0

    collection = get_citic_daily_collection()
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


def list_latest_citic_trade_dates(
    *,
    limit: int = 5,
    before_or_on: str | None = None,
    level: int | None = None,
) -> list[str]:
    if limit <= 0:
        return []

    query: dict[str, object] = {}
    if before_or_on:
        query["trade_date"] = {"$lte": before_or_on}
    if level is not None:
        query["level"] = level

    collection = get_citic_daily_collection()
    dates = collection.distinct("trade_date", query)
    dates = sorted((d for d in dates if d), reverse=True)
    return dates[:limit]


def list_citic_trade_dates(limit: int = 30) -> list[str]:
    return list_latest_citic_trade_dates(limit=limit)


def get_citic_daily_rankings(
    *,
    trade_date: str,
    level: int,
    top_n: int = 5,
    bottom_n: int = 5,
) -> tuple[list[dict[str, object]], list[dict[str, object]], int]:
    if not trade_date:
        return [], [], 0

    collection = get_citic_daily_collection()
    query = {"trade_date": trade_date, "level": level}
    total = collection.count_documents(query)
    projection = {
        "_id": 0,
        "ts_code": 1,
        "name": 1,
        "pct_change": 1,
        "rank": 1,
        "rank_total": 1,
        "close": 1,
        "vol": 1,
        "amount": 1,
    }

    top = list(
        collection.find(query, projection)
        .sort([("pct_change", -1), ("ts_code", ASCENDING)])
        .limit(max(top_n, 0))
    )
    bottom = list(
        collection.find(query, projection)
        .sort([("pct_change", ASCENDING), ("ts_code", ASCENDING)])
        .limit(max(bottom_n, 0))
    )
    return top, bottom, int(total)


def build_citic_avg_rankings(
    *,
    trade_dates: list[str],
    level: int,
    top_n: int = 10,
    bottom_n: int = 10,
) -> dict[str, object]:
    if not trade_dates:
        return {"trade_dates": [], "strongest": [], "weakest": []}

    collection = get_citic_daily_collection()
    query = {"trade_date": {"$in": trade_dates}, "level": level}
    projection = {
        "_id": 0,
        "ts_code": 1,
        "name": 1,
        "trade_date": 1,
        "rank": 1,
        "pct_change": 1,
    }
    rows = list(collection.find(query, projection))
    if not rows:
        return {"trade_dates": trade_dates, "strongest": [], "weakest": []}

    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    name_map: dict[str, str] = {}
    for row in rows:
        ts_code = row.get("ts_code")
        if not ts_code:
            continue
        grouped[ts_code].append(row)
        if row.get("name"):
            name_map[ts_code] = row.get("name")

    trade_dates_ordered = list(trade_dates)
    results: list[dict[str, object]] = []
    for ts_code, items in grouped.items():
        rank_by_date = {item.get("trade_date"): item.get("rank") for item in items}
        pct_by_date = {item.get("trade_date"): item.get("pct_change") for item in items}
        ranks = [rank_by_date.get(date) for date in trade_dates_ordered]
        pcts = [pct_by_date.get(date) for date in trade_dates_ordered]

        valid_ranks = [r for r in ranks if isinstance(r, (int, float))]
        if not valid_ranks:
            continue

        valid_pcts = [p for p in pcts if isinstance(p, (int, float))]
        results.append(
            {
                "ts_code": ts_code,
                "name": name_map.get(ts_code),
                "level": level,
                "rank_day1": ranks[0] if len(ranks) > 0 else None,
                "rank_day2": ranks[1] if len(ranks) > 1 else None,
                "rank_day3": ranks[2] if len(ranks) > 2 else None,
                "rank_day4": ranks[3] if len(ranks) > 3 else None,
                "rank_day5": ranks[4] if len(ranks) > 4 else None,
                "rank_avg": sum(valid_ranks) / len(valid_ranks),
                "pct_day1": pcts[0] if len(pcts) > 0 else None,
                "pct_day2": pcts[1] if len(pcts) > 1 else None,
                "pct_day3": pcts[2] if len(pcts) > 2 else None,
                "pct_day4": pcts[3] if len(pcts) > 3 else None,
                "pct_day5": pcts[4] if len(pcts) > 4 else None,
                "pct_sum": sum(valid_pcts),
            }
        )

    strongest = sorted(results, key=lambda x: (x.get("rank_avg") or 0))[: max(top_n, 0)]
    weakest = sorted(results, key=lambda x: (x.get("rank_avg") or 0), reverse=True)[
        : max(bottom_n, 0)
    ]
    return {"trade_dates": trade_dates_ordered, "strongest": strongest, "weakest": weakest}


def get_citic_level_member_totals() -> dict[str, object]:
    collection = get_citic_daily_collection()
    levels: list[dict[str, object]] = []
    latest_common: str | None = None
    for level in [1, 2, 3]:
        dates = list_latest_citic_trade_dates(limit=1, level=level)
        trade_date = dates[0] if dates else None
        count = 0
        if trade_date:
            count = int(collection.count_documents({"trade_date": trade_date, "level": level}))
            if latest_common is None or str(trade_date) > str(latest_common):
                latest_common = str(trade_date)
        levels.append({"level": level, "trade_date": trade_date, "member_total": count})
    return {"latest_trade_date": latest_common, "levels": levels}
