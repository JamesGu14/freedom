#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
from pathlib import Path

import pandas as pd
from pymongo import UpdateOne

SCRIPT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(SCRIPT_ROOT))

from app.core.config import settings  # noqa: E402
from app.data.mongo_shenwan_member import (  # noqa: E402
    bulk_update_members,
    list_shenwan_members,
    upsert_shenwan_members,
)
from app.data.tushare_client import fetch_shenwan_members  # noqa: E402

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync Shenwan industry members from TuShare into MongoDB."
    )
    parser.add_argument("--version", type=str, default="2021", help="Version tag to store")
    parser.add_argument("--l1-code", type=str, default="", help="Filter by l1_code")
    parser.add_argument("--l2-code", type=str, default="", help="Filter by l2_code")
    parser.add_argument("--l3-code", type=str, default="", help="Filter by l3_code")
    parser.add_argument("--ts-code", type=str, default="", help="Filter by ts_code")
    parser.add_argument(
        "--is-new",
        type=str,
        default="Y",
        choices=["Y", "N", "ALL"],
        help="Sync only new(Y), history(N), or all",
    )
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="Compare latest members and mark removed ones (only for is_new=Y without filters)",
    )
    return parser.parse_args()


def _normalize_date(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None
    if text.isdigit() and len(text) == 8:
        return text
    return text


def _to_records(df: pd.DataFrame) -> list[dict[str, object]]:
    if df is None or df.empty:
        return []
    normalized = df.where(pd.notna(df), None)
    return normalized.to_dict(orient="records")


def _build_records(rows: list[dict[str, object]], version: str) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for row in rows:
        in_date = _normalize_date(row.get("in_date"))
        out_date = _normalize_date(row.get("out_date"))
        is_new = str(row.get("is_new") or "").upper() or "Y"
        record = {
            "ts_code": row.get("ts_code"),
            "name": row.get("name"),
            "l1_code": row.get("l1_code"),
            "l1_name": row.get("l1_name"),
            "l2_code": row.get("l2_code"),
            "l2_name": row.get("l2_name"),
            "l3_code": row.get("l3_code"),
            "l3_name": row.get("l3_name"),
            "in_date": in_date,
            "out_date": out_date,
            "is_new": is_new,
            "version": version,
        }
        if record["ts_code"] and record["l3_code"] and record["in_date"]:
            records.append(record)
    return records


def _validate_member_records(records: list[dict[str, object]]) -> None:
    invalid_out_date = 0
    invalid_date_order = 0
    for record in records:
        is_new = record.get("is_new")
        in_date = record.get("in_date")
        out_date = record.get("out_date")
        if is_new == "Y" and out_date:
            invalid_out_date += 1
        if is_new == "N" and not out_date:
            invalid_out_date += 1
        if in_date and out_date and str(in_date) >= str(out_date):
            invalid_date_order += 1
    if invalid_out_date:
        logger.warning("%s records violate is_new/out_date rules", invalid_out_date)
    if invalid_date_order:
        logger.warning("%s records have in_date >= out_date", invalid_date_order)


def _sync_latest_members(
    *,
    version: str,
    l1_code: str,
    l2_code: str,
    l3_code: str,
    ts_code: str,
    is_new: str,
) -> list[dict[str, object]]:
    df = fetch_shenwan_members(
        l1_code=l1_code or None,
        l2_code=l2_code or None,
        l3_code=l3_code or None,
        ts_code=ts_code or None,
        is_new=is_new if is_new != "ALL" else None,
    )
    rows = _to_records(df)
    records = _build_records(rows, version)
    _validate_member_records(records)
    return records


def _mark_removed_members(
    *,
    version: str,
    current_members: list[dict[str, object]],
    latest_members: list[dict[str, object]],
) -> int:
    today = dt.datetime.now().strftime("%Y%m%d")
    latest_keys = {(item["ts_code"], item["l3_code"]) for item in latest_members}
    updates: list[UpdateOne] = []
    for member in current_members:
        key = (member.get("ts_code"), member.get("l3_code"))
        if key in latest_keys:
            continue
        if not member.get("in_date"):
            continue
        updates.append(
            UpdateOne(
                {
                    "ts_code": member.get("ts_code"),
                    "l3_code": member.get("l3_code"),
                    "in_date": member.get("in_date"),
                    "version": version,
                },
                {"$set": {"is_new": "N", "out_date": today, "updated_at": dt.datetime.now(dt.UTC)}},
            )
        )
    return bulk_update_members(updates)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    args = parse_args()
    if not settings.tushare_token:
        raise SystemExit("TUSHARE_TOKEN is required")

    is_new = args.is_new.upper()
    records = _sync_latest_members(
        version=args.version,
        l1_code=args.l1_code,
        l2_code=args.l2_code,
        l3_code=args.l3_code,
        ts_code=args.ts_code,
        is_new=is_new,
    )
    upserted = upsert_shenwan_members(records)
    logger.info("upserted member records=%s", upserted)

    incremental_allowed = (
        is_new == "Y"
        and not args.l1_code
        and not args.l2_code
        and not args.l3_code
        and not args.ts_code
    )
    if args.incremental and incremental_allowed:
        current_members, _ = list_shenwan_members(
            version=args.version, is_new="Y", page=1, page_size=200000
        )
        updated = _mark_removed_members(
            version=args.version,
            current_members=current_members,
            latest_members=records,
        )
        logger.info("marked removed member records=%s", updated)
    elif args.incremental and not incremental_allowed:
        logger.info("skip incremental: only allowed when syncing full latest members (is_new=Y)")


if __name__ == "__main__":
    main()
