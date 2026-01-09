#!/usr/bin/env python3
from __future__ import annotations

import argparse
import uuid
from pathlib import Path

import duckdb

from app.core.config import settings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compact daily parquet partitions into a single file per stock/year."
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


def iter_partitions(base_dir: Path, ts_code: str | None, year: str | None) -> list[Path]:
    partitions: list[Path] = []
    ts_dirs = [base_dir / f"ts_code={ts_code}"] if ts_code else sorted(base_dir.glob("ts_code=*"))
    for ts_dir in ts_dirs:
        if not ts_dir.is_dir():
            continue
        year_dirs = [ts_dir / f"year={year}"] if year else sorted(ts_dir.glob("year=*"))
        for year_dir in year_dirs:
            if year_dir.is_dir():
                partitions.append(year_dir)
    return partitions


def compact_partition(partition_dir: Path) -> tuple[int, int]:
    parts = sorted(partition_dir.glob("part-*.parquet"))
    if len(parts) <= 1:
        return 0, 0

    tmp_path = partition_dir / f"compact-{uuid.uuid4().hex}.parquet"
    part_glob = str(partition_dir / "part-*.parquet")
    with duckdb.connect() as con:
        part_glob_sql = part_glob.replace("'", "''")
        tmp_path_sql = str(tmp_path).replace("'", "''")
        con.execute(
            f"COPY (SELECT DISTINCT * FROM read_parquet('{part_glob_sql}') "
            f"ORDER BY trade_date) "
            f"TO '{tmp_path_sql}' (FORMAT 'parquet')"
        )

    removed = 0
    for part in parts:
        part.unlink()
        removed += 1

    final_path = partition_dir / "part-0000.parquet"
    tmp_path.replace(final_path)
    return removed, 1


def main() -> None:
    args = parse_args()
    base_dir = settings.data_dir / "raw" / "daily"
    if not base_dir.exists():
        raise SystemExit(f"Base directory not found: {base_dir}")

    ts_code = args.ts_code.strip() or None
    year = args.year.strip() or None

    partitions = iter_partitions(base_dir, ts_code, year)
    if not partitions:
        raise SystemExit("No partitions found to compact")

    total_removed = 0
    total_written = 0
    for partition_dir in partitions:
        removed, written = compact_partition(partition_dir)
        if removed:
            print(f"{partition_dir} removed={removed} written={written}")
        total_removed += removed
        total_written += written

    print(f"done removed={total_removed} written={total_written}")


if __name__ == "__main__":
    main()
