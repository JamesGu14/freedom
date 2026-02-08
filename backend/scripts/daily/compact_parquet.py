#!/usr/bin/env python3
"""Compact fragmented Hive-partitioned parquet directories into one file per partition.

Supports datasets: daily, daily_basic, daily_limit, indicators, all.
Deduplicates by (ts_code, trade_date), keeping the record from the latest file.
Crash-safe: writes to temp file, renames to final, then deletes old parts.
"""
from __future__ import annotations

import argparse
import logging
import uuid
from pathlib import Path

import duckdb

from app.core.config import settings

logger = logging.getLogger(__name__)

DATASET_DIRS = {
    "daily": "raw/daily",
    "daily_basic": "raw/daily_basic",
    "daily_limit": "raw/daily_limit",
    "indicators": "features/indicators",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compact parquet partitions into a single file per stock/year."
    )
    parser.add_argument(
        "--dataset",
        type=str,
        required=True,
        choices=[*DATASET_DIRS.keys(), "all"],
        help="Which dataset to compact (or 'all' for every dataset)",
    )
    parser.add_argument(
        "--ts-code",
        type=str,
        default="",
        help="Limit to a single ts_code (e.g. 000001.SZ)",
    )
    parser.add_argument(
        "--year",
        type=str,
        default="",
        help="Limit to a single year (e.g. 2024)",
    )
    return parser.parse_args()


def iter_partitions(
    base_dir: Path, ts_code: str | None, year: str | None
) -> list[Path]:
    partitions: list[Path] = []
    ts_dirs = (
        [base_dir / f"ts_code={ts_code}"]
        if ts_code
        else sorted(base_dir.glob("ts_code=*"))
    )
    for ts_dir in ts_dirs:
        if not ts_dir.is_dir():
            continue
        year_dirs = (
            [ts_dir / f"year={year}"] if year else sorted(ts_dir.glob("year=*"))
        )
        for year_dir in year_dirs:
            if year_dir.is_dir():
                partitions.append(year_dir)
    return partitions


def cleanup_stale_temps(partition_dir: Path) -> int:
    """Remove leftover compact-*.parquet files from previous crashed runs."""
    removed = 0
    for tmp in partition_dir.glob("compact-*.parquet"):
        tmp.unlink()
        removed += 1
    return removed


def compact_partition(partition_dir: Path) -> tuple[int, int]:
    """Compact all part-*.parquet files in a partition directory into one.

    Returns (files_removed, files_written).
    """
    cleanup_stale_temps(partition_dir)

    parts = sorted(partition_dir.glob("part-*.parquet"))
    if len(parts) <= 1:
        return 0, 0

    tmp_path = partition_dir / f"compact-{uuid.uuid4().hex}.parquet"
    part_glob = str(partition_dir / "part-*.parquet")

    with duckdb.connect() as con:
        part_glob_sql = part_glob.replace("'", "''")
        tmp_path_sql = str(tmp_path).replace("'", "''")

        # Use filename=true so we can ORDER BY filename DESC to keep latest file's record
        select_sql = (
            "SELECT * EXCLUDE (filename) "
            "FROM read_parquet('{glob}', filename=true, union_by_name=true) "
            "QUALIFY row_number() OVER "
            "(PARTITION BY ts_code, trade_date ORDER BY filename DESC) = 1"
        ).format(glob=part_glob_sql)
        order_sql = " ORDER BY ts_code, trade_date"

        # Safety check: count before and after dedup
        before_count = con.execute(
            f"SELECT COUNT(*) FROM read_parquet('{part_glob_sql}', union_by_name=true)"
        ).fetchone()[0]
        after_count = con.execute(
            f"SELECT COUNT(*) FROM ({select_sql})"
        ).fetchone()[0]

        # Write compacted file
        con.execute(
            f"COPY ({select_sql}{order_sql}) TO '{tmp_path_sql}' (FORMAT 'parquet')"
        )

        # Verify written file
        written_count = con.execute(
            f"SELECT COUNT(*) FROM read_parquet('{tmp_path_sql}')"
        ).fetchone()[0]

        if written_count != after_count:
            tmp_path.unlink(missing_ok=True)
            raise RuntimeError(
                f"row count mismatch for {partition_dir}: "
                f"expected={after_count} wrote={written_count}"
            )
        if before_count > 0 and written_count == 0:
            tmp_path.unlink(missing_ok=True)
            raise RuntimeError(f"empty output for {partition_dir}")

    # Crash-safe: rename temp to final FIRST, then delete old parts
    final_path = partition_dir / "part-0000.parquet"
    tmp_path.replace(final_path)

    removed = 0
    for part in parts:
        if part.name != "part-0000.parquet":
            part.unlink()
            removed += 1
        # part-0000.parquet was already overwritten by rename above

    return removed, 1


def compact_dataset(
    dataset: str, ts_code: str | None, year: str | None
) -> tuple[int, int]:
    rel_dir = DATASET_DIRS[dataset]
    base_dir = settings.data_dir / rel_dir
    if not base_dir.exists():
        logger.info("[SKIP] %s: directory not found (%s)", dataset, base_dir)
        return 0, 0

    partitions = iter_partitions(base_dir, ts_code, year)
    if not partitions:
        logger.info("[SKIP] %s: no partitions found", dataset)
        return 0, 0

    logger.info("[%s] compacting partitions=%s", dataset, len(partitions))
    total_removed = 0
    total_written = 0
    for partition_dir in partitions:
        removed, written = compact_partition(partition_dir)
        if removed:
            logger.info("  %s removed=%s", partition_dir.relative_to(base_dir), removed)
        total_removed += removed
        total_written += written

    logger.info("[%s] done: removed=%s compacted=%s", dataset, total_removed, total_written)
    return total_removed, total_written


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    args = parse_args()
    ts_code = args.ts_code.strip() or None
    year = args.year.strip() or None

    datasets = list(DATASET_DIRS.keys()) if args.dataset == "all" else [args.dataset]

    grand_removed = 0
    grand_written = 0
    for ds in datasets:
        removed, written = compact_dataset(ds, ts_code, year)
        grand_removed += removed
        grand_written += written

    logger.info("[total] removed=%s compacted=%s", grand_removed, grand_written)


if __name__ == "__main__":
    main()
