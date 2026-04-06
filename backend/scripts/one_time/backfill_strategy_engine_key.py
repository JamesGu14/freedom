#!/usr/bin/env python3
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from pymongo import UpdateOne

SCRIPT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(SCRIPT_ROOT))

from app.data.mongo import get_collection  # noqa: E402
from app.data.mongo_backtest import ensure_strategy_backtest_indexes  # noqa: E402

logger = logging.getLogger(__name__)
DEFAULT_STRATEGY_KEY = "multifactor_v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill strategy_key/params_schema_version for strategy collections.")
    parser.add_argument("--dry-run", action="store_true", help="Print changes only, do not write MongoDB")
    return parser.parse_args()


def _resolve_key(value: object) -> str:
    text = str(value or "").strip()
    return text or DEFAULT_STRATEGY_KEY


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    args = parse_args()
    ensure_strategy_backtest_indexes()

    definitions = get_collection("strategy_definitions")
    versions = get_collection("strategy_versions")

    version_rows = list(
        versions.find(
            {},
            {
                "_id": 0,
                "strategy_version_id": 1,
                "strategy_id": 1,
                "strategy_key": 1,
                "params_schema_version": 1,
                "params_snapshot": 1,
            },
        )
    )

    strategy_key_map: dict[str, set[str]] = {}
    version_ops: list[UpdateOne] = []
    for row in version_rows:
        strategy_id = str(row.get("strategy_id") or "").strip()
        strategy_version_id = str(row.get("strategy_version_id") or "").strip()
        if not strategy_id or not strategy_version_id:
            continue
        resolved_key = _resolve_key(row.get("strategy_key") or (row.get("params_snapshot") or {}).get("strategy_key"))
        strategy_key_map.setdefault(strategy_id, set()).add(resolved_key)

        update_fields: dict[str, object] = {}
        if str(row.get("strategy_key") or "").strip() != resolved_key:
            update_fields["strategy_key"] = resolved_key
        if not str(row.get("params_schema_version") or "").strip():
            update_fields["params_schema_version"] = "v1"

        if update_fields:
            version_ops.append(
                UpdateOne(
                    {"strategy_version_id": strategy_version_id},
                    {"$set": update_fields},
                    upsert=False,
                )
            )

    definition_rows = list(
        definitions.find(
            {},
            {
                "_id": 0,
                "strategy_id": 1,
                "strategy_key": 1,
            },
        )
    )

    definition_ops: list[UpdateOne] = []
    conflicts: list[dict[str, object]] = []
    for row in definition_rows:
        strategy_id = str(row.get("strategy_id") or "").strip()
        if not strategy_id:
            continue

        key_set = strategy_key_map.get(strategy_id, set())
        if len(key_set) > 1:
            conflicts.append({"strategy_id": strategy_id, "strategy_keys": sorted(key_set)})

        existing_key = str(row.get("strategy_key") or "").strip()
        if existing_key:
            target_key = existing_key
        elif len(key_set) == 1:
            target_key = next(iter(key_set))
        else:
            target_key = DEFAULT_STRATEGY_KEY

        if existing_key != target_key:
            definition_ops.append(
                UpdateOne(
                    {"strategy_id": strategy_id},
                    {"$set": {"strategy_key": target_key}},
                    upsert=False,
                )
            )

    logger.info(
        "backfill preview: definition_updates=%s version_updates=%s conflicts=%s dry_run=%s",
        len(definition_ops),
        len(version_ops),
        len(conflicts),
        args.dry_run,
    )

    for item in conflicts:
        logger.warning("strategy_key conflict: strategy_id=%s keys=%s", item["strategy_id"], ",".join(item["strategy_keys"]))

    if args.dry_run:
        return

    if definition_ops:
        definitions.bulk_write(definition_ops, ordered=False)
    if version_ops:
        versions.bulk_write(version_ops, ordered=False)

    logger.info("backfill done: definitions=%s versions=%s", len(definition_ops), len(version_ops))


if __name__ == "__main__":
    main()
