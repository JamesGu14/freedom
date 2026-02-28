#!/usr/bin/env python3
"""从 Parquet 与 MongoDB 扫描已同步日期，回填到 data_sync_date 集合。幂等，可重复执行。"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(SCRIPT_ROOT))

import duckdb
from pymongo import UpdateOne

from app.core.config import settings  # noqa: E402
from app.data.mongo import get_collection  # noqa: E402
from app.data.mongo_data_sync_date import ensure_data_sync_date_indexes  # noqa: E402

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill data_sync_date from Parquet and MongoDB (idempotent)."
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="Data directory (default: settings.data_dir)",
    )
    return parser.parse_args()


def _distinct_trade_dates_from_parquet(parquet_dir: Path) -> list[str]:
    """扫描 Parquet 目录，返回 DISTINCT trade_date 列表。"""
    if not parquet_dir.exists() or not parquet_dir.is_dir():
        return []
    files = list(parquet_dir.rglob("part-*.parquet"))
    if not files:
        return []
    paths = [str(p) for p in files]
    try:
        with duckdb.connect() as con:
            df = con.execute(
                "SELECT DISTINCT trade_date::VARCHAR AS trade_date FROM read_parquet(?, union_by_name=true)",
                [paths],
            ).fetchdf()
    except Exception as e:
        logger.warning("DuckDB read_parquet %s failed: %s", parquet_dir, e)
        return []
    dates = df["trade_date"].astype(str).str.replace("-", "", regex=False).tolist()
    return sorted(set(dates))


def _upsert_sync_dates(task: str, trade_dates: list[str]) -> int:
    """批量 upsert (trade_date, task)，返回写入条数。"""
    if not trade_dates:
        return 0
    ensure_data_sync_date_indexes()
    coll = get_collection("data_sync_date")
    now = dt.datetime.now(dt.UTC)

    bulk_ops = []
    for d in trade_dates:
        d = str(d).strip().replace("-", "")
        if len(d) != 8 or not d.isdigit():
            continue
        bulk_ops.append(
            UpdateOne(
                {"trade_date": d, "task": task},
                {"$set": {"trade_date": d, "task": task, "completed_at": now}},
                upsert=True,
            )
        )
    if not bulk_ops:
        return 0
    result = coll.bulk_write(bulk_ops, ordered=False)
    return result.upserted_count + result.modified_count


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    args = parse_args()
    data_dir = args.data_dir or settings.data_dir
    data_dir = Path(data_dir)
    if not data_dir.is_dir():
        logger.error("Data dir not found: %s", data_dir)
        sys.exit(1)

    ensure_data_sync_date_indexes()

    # 1) pull_daily: from raw/daily parquet
    daily_dates = _distinct_trade_dates_from_parquet(data_dir / "raw" / "daily")
    n = _upsert_sync_dates("pull_daily", daily_dates)
    logger.info("pull_daily: scanned %s dates, upserted %s", len(daily_dates), n)

    # 2) sync_stk_factor_pro: from features/indicators parquet
    indicator_dates = _distinct_trade_dates_from_parquet(data_dir / "features" / "indicators")
    n = _upsert_sync_dates("sync_stk_factor_pro", indicator_dates)
    logger.info("sync_stk_factor_pro: scanned %s dates, upserted %s", len(indicator_dates), n)

    # 3) sync_shenwan_daily: from MongoDB shenwan_daily
    coll_sw = get_collection("shenwan_daily")
    shenwan_dates = list(coll_sw.distinct("trade_date"))
    shenwan_dates = [str(d) for d in shenwan_dates if d]
    n = _upsert_sync_dates("sync_shenwan_daily", shenwan_dates)
    logger.info("sync_shenwan_daily: scanned %s dates, upserted %s", len(shenwan_dates), n)

    # 4) sync_zhishu_data: from MongoDB citic_daily, market_index_dailybasic, index_factor_pro (union)
    all_zhishu = set()
    for cname in ("citic_daily", "market_index_dailybasic", "index_factor_pro"):
        try:
            dates = get_collection(cname).distinct("trade_date")
            all_zhishu.update(str(d) for d in dates if d)
        except Exception as e:
            logger.warning("distinct trade_date from %s failed: %s", cname, e)
    zhishu_dates = sorted(all_zhishu)
    n = _upsert_sync_dates("sync_zhishu_data", zhishu_dates)
    logger.info("sync_zhishu_data: scanned %s dates (union), upserted %s", len(zhishu_dates), n)

    logger.info("backfill_data_sync_date done")


if __name__ == "__main__":
    main()
