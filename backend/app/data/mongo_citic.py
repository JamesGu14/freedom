from __future__ import annotations

import datetime as dt

from pymongo import ASCENDING, UpdateOne

from app.data.mongo import get_collection

_INDUSTRY_INDEX_READY = False
_MEMBER_INDEX_READY = False


def _ensure_citic_industry_indexes() -> None:
    collection = get_collection("citic_industry")
    collection.create_index(
        [("index_code", ASCENDING)],
        unique=True,
        name="idx_index_code_unique",
    )
    collection.create_index(
        [("level", ASCENDING), ("industry_name", ASCENDING)],
        name="idx_level_name",
    )


def _ensure_citic_member_indexes() -> None:
    collection = get_collection("citic_industry_member")
    collection.create_index(
        [("cons_code", ASCENDING), ("index_code", ASCENDING), ("in_date", ASCENDING)],
        unique=True,
        name="idx_cons_index_indate",
    )
    collection.create_index(
        [("index_code", ASCENDING), ("is_new", ASCENDING)],
        name="idx_index_isnew",
    )
    collection.create_index(
        [("cons_code", ASCENDING), ("is_new", ASCENDING)],
        name="idx_cons_isnew",
    )
    collection.create_index(
        [("level", ASCENDING), ("is_new", ASCENDING)],
        name="idx_level_isnew",
    )
    collection.create_index(
        [("in_date", ASCENDING), ("out_date", ASCENDING), ("cons_code", ASCENDING)],
        name="idx_active_window_conscode",
    )


def get_citic_industry_collection():
    global _INDUSTRY_INDEX_READY
    if not _INDUSTRY_INDEX_READY:
        _ensure_citic_industry_indexes()
        _INDUSTRY_INDEX_READY = True
    return get_collection("citic_industry")


def get_citic_member_collection():
    global _MEMBER_INDEX_READY
    if not _MEMBER_INDEX_READY:
        _ensure_citic_member_indexes()
        _MEMBER_INDEX_READY = True
    return get_collection("citic_industry_member")


def upsert_citic_industry(records: list[dict[str, object]]) -> int:
    if not records:
        return 0

    collection = get_citic_industry_collection()
    ops: list[UpdateOne] = []
    now = dt.datetime.now(dt.UTC)
    for record in records:
        record.pop("_id", None)
        record.pop("created_at", None)
        index_code = record.get("index_code")
        if not index_code:
            continue
        record["updated_at"] = now
        ops.append(
            UpdateOne(
                {"index_code": index_code},
                {"$set": record, "$setOnInsert": {"created_at": now}},
                upsert=True,
            )
        )
    if not ops:
        return 0

    collection.bulk_write(ops, ordered=False)
    return len(ops)


def upsert_citic_members(records: list[dict[str, object]]) -> int:
    if not records:
        return 0

    collection = get_citic_member_collection()
    ops: list[UpdateOne] = []
    now = dt.datetime.now(dt.UTC)
    for record in records:
        record.pop("_id", None)
        record.pop("created_at", None)
        cons_code = record.get("cons_code")
        index_code = record.get("index_code")
        in_date = record.get("in_date")
        if not cons_code or not index_code or not in_date:
            continue
        record["updated_at"] = now
        ops.append(
            UpdateOne(
                {"cons_code": cons_code, "index_code": index_code, "in_date": in_date},
                {"$set": record, "$setOnInsert": {"created_at": now}},
                upsert=True,
            )
        )
    if not ops:
        return 0

    collection.bulk_write(ops, ordered=False)
    return len(ops)


def list_citic_industry(
    *,
    level: int | None = None,
) -> list[dict[str, object]]:
    query: dict[str, object] = {}
    if level is not None:
        query["level"] = level
    collection = get_citic_industry_collection()
    cursor = collection.find(query, {"_id": 0}).sort(
        [("level", ASCENDING), ("industry_name", ASCENDING)]
    )
    return list(cursor)


def get_citic_by_index_code(index_code: str) -> dict[str, object] | None:
    if not index_code:
        return None
    collection = get_citic_industry_collection()
    return collection.find_one({"index_code": index_code}, {"_id": 0})


def list_citic_members(
    *,
    index_code: str | None = None,
    cons_code: str | None = None,
    level: int | None = None,
    is_new: str | None = "Y",
    page: int = 1,
    page_size: int = 200,
) -> tuple[list[dict[str, object]], int]:
    query: dict[str, object] = {}
    if index_code:
        query["index_code"] = index_code
    if cons_code:
        query["cons_code"] = cons_code
    if level is not None:
        query["level"] = level
    if is_new:
        query["is_new"] = is_new

    offset = max(page - 1, 0) * page_size
    collection = get_citic_member_collection()
    total = collection.count_documents(query)
    cursor = (
        collection.find(query, {"_id": 0})
        .sort([("cons_code", ASCENDING), ("index_code", ASCENDING), ("in_date", ASCENDING)])
        .skip(offset)
        .limit(page_size)
    )
    return list(cursor), int(total)
