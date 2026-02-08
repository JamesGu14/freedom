#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
import time
from pathlib import Path

import pandas as pd

SCRIPT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(SCRIPT_ROOT))

from app.core.config import settings  # noqa: E402
from app.data.mongo_shenwan import upsert_shenwan_industry  # noqa: E402
from app.data.tushare_client import fetch_shenwan_classify  # noqa: E402

logger = logging.getLogger(__name__)

VERSION_SRC = {
    "2014": "SW2014",
    "2021": "SW2021",
}

LEVEL_NAME = {
    1: "一级行业",
    2: "二级行业",
    3: "三级行业",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync Shenwan industry classify data from TuShare into MongoDB."
    )
    parser.add_argument(
        "--version",
        type=str,
        default="all",
        choices=["2014", "2021", "all"],
        help="Sync which version (default: all)",
    )
    parser.add_argument("--sleep", type=float, default=0.3, help="Sleep seconds between calls")
    return parser.parse_args()


def _to_records(df: pd.DataFrame) -> list[dict[str, object]]:
    if df is None or df.empty:
        return []
    normalized = df.where(pd.notna(df), None)
    return normalized.to_dict(orient="records")


def _pick(row: dict[str, object], keys: list[str]) -> object | None:
    for key in keys:
        if key in row and row[key] is not None:
            return row[key]
    return None


def _parse_level(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip().upper()
    if text in {"1", "L1", "一级行业", "一级"}:
        return 1
    if text in {"2", "L2", "二级行业", "二级"}:
        return 2
    if text in {"3", "L3", "三级行业", "三级"}:
        return 3
    return None


def _derive_level1_code(industry_code: str | None) -> str | None:
    if not industry_code or len(industry_code) < 2:
        return None
    return f"{industry_code[:2]}0000"


def _derive_level2_code(industry_code: str | None) -> str | None:
    if not industry_code or len(industry_code) < 4:
        return None
    return f"{industry_code[:4]}00"


def _to_bool(value: object) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "y", "yes"}:
        return True
    if text in {"0", "false", "n", "no"}:
        return False
    return None


def _to_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def build_level_records(
    df: pd.DataFrame,
    *,
    version: str,
    default_level: int,
) -> list[dict[str, object]]:
    rows = _to_records(df)
    records: list[dict[str, object]] = []
    now = dt.datetime.now(dt.UTC)
    for row in rows:
        industry_code = _pick(row, ["industry_code", "行业代码"])
        if not industry_code:
            continue
        industry_code = str(industry_code)

        level_value = _parse_level(_pick(row, ["level", "指数类别"]))
        level_num = level_value or default_level

        level1_code = _pick(row, ["level1_code", "l1_code", "一级行业代码"])
        level2_code = _pick(row, ["level2_code", "l2_code", "二级行业代码"])

        level1_code = str(level1_code) if level1_code else None
        level2_code = str(level2_code) if level2_code else None

        if level_num == 1:
            level1_code = industry_code
            level2_code = None
        elif level_num == 2:
            level2_code = industry_code
            level1_code = level1_code or _derive_level1_code(industry_code)
        else:
            level2_code = level2_code or _derive_level2_code(industry_code)
            level1_code = level1_code or _derive_level1_code(industry_code)

        parent_code = _pick(row, ["parent_code", "父级行业代码"])
        if parent_code:
            parent_code = str(parent_code)
        elif level_num == 2:
            parent_code = level1_code
        elif level_num == 3:
            parent_code = level2_code
        else:
            parent_code = None

        level1_name = _pick(row, ["level1_name", "l1_name", "一级行业"])
        level2_name = _pick(row, ["level2_name", "l2_name", "二级行业"])
        level3_name = _pick(row, ["level3_name", "l3_name", "三级行业"])
        industry_name = _pick(row, ["industry_name", "行业名称"])

        if level_num == 1:
            industry_name = industry_name or level1_name
        elif level_num == 2:
            industry_name = industry_name or level2_name
        else:
            industry_name = industry_name or level3_name

        record = {
            "industry_code": industry_code,
            "index_code": _pick(row, ["index_code", "指数代码"]),
            "industry_name": industry_name,
            "level": level_num,
            "level_name": LEVEL_NAME.get(level_num),
            "parent_code": parent_code,
            "level1_code": level1_code,
            "level1_name": level1_name,
            "level2_code": level2_code if level_num >= 2 else None,
            "level2_name": level2_name,
            "version": version,
            "version_note": _pick(row, ["version_note", "变动原因"]),
            "is_published": _to_bool(_pick(row, ["is_pub", "是否发布"])),
            "constituent_count": _to_int(_pick(row, ["con_num", "cons_num", "成分股数"])),
            "created_at": now,
            "updated_at": now,
        }
        records.append(record)
    return records


def fill_missing_names(
    records: list[dict[str, object]],
    level1_map: dict[str, str],
    level2_map: dict[str, str],
) -> None:
    for record in records:
        level1_code = record.get("level1_code")
        if level1_code and not record.get("level1_name"):
            record["level1_name"] = level1_map.get(level1_code)
        level2_code = record.get("level2_code")
        if level2_code and not record.get("level2_name"):
            record["level2_name"] = level2_map.get(level2_code)


def validate_relationships(records: list[dict[str, object]]) -> None:
    code_set = {record.get("industry_code") for record in records if record.get("industry_code")}
    missing_parent = 0
    for record in records:
        level = record.get("level")
        if level == 1:
            continue
        parent_code = record.get("parent_code")
        if not parent_code:
            missing_parent += 1
            continue
        if parent_code not in code_set:
            missing_parent += 1
    if missing_parent:
        logger.warning("missing parent linkage count=%s", missing_parent)


def fetch_version_records(version: str, sleep_seconds: float) -> list[dict[str, object]]:
    src = VERSION_SRC[version]
    all_records: list[dict[str, object]] = []

    level_data: dict[int, list[dict[str, object]]] = {}
    for level_code, level_num in [("L1", 1), ("L2", 2), ("L3", 3)]:
        df = fetch_shenwan_classify(src=src, level=level_code)
        records = build_level_records(df, version=version, default_level=level_num)
        level_data[level_num] = records
        all_records.extend(records)
        logger.info("version=%s level=%s rows=%s", version, level_code, len(records))
        time.sleep(sleep_seconds)

    level1_map = {
        record["industry_code"]: record["industry_name"]
        for record in level_data.get(1, [])
        if record.get("industry_code") and record.get("industry_name")
    }
    level2_map = {
        record["industry_code"]: record["industry_name"]
        for record in level_data.get(2, [])
        if record.get("industry_code") and record.get("industry_name")
    }
    fill_missing_names(all_records, level1_map, level2_map)
    validate_relationships(all_records)
    return all_records


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    args = parse_args()
    if not settings.tushare_token:
        raise SystemExit("TUSHARE_TOKEN is required")

    if args.version == "all":
        versions = ["2014", "2021"]
    else:
        versions = [args.version]

    total_records = 0
    for version in versions:
        logger.info("fetching version=%s", version)
        records = fetch_version_records(version, args.sleep)
        inserted = upsert_shenwan_industry(records)
        total_records += inserted
        logger.info("version=%s upserted=%s", version, inserted)

    logger.info("sync_shenwan_industry done, upserted=%s", total_records)


if __name__ == "__main__":
    main()
