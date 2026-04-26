#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
import time
from pathlib import Path

from tqdm import tqdm

SCRIPT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(SCRIPT_ROOT))

from app.core.config import settings  # noqa: E402
from app.data.duckdb_store import get_connection  # noqa: E402
from app.data.duckdb_financials import ensure_financial_tables, upsert_fina_audit  # noqa: E402
from app.data.mongo_data_sync_date import mark_sync_done  # noqa: E402
from app.data.mongo_stock import list_stock_codes  # noqa: E402
from app.data.tushare_client import fetch_fina_audit  # noqa: E402

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync TuShare fina_audit data into DuckDB.")
    parser.add_argument("--mode", choices=["daily", "full"], default="daily", help="daily uses disclosure_date to reduce stock scope; full scans all stocks")
    parser.add_argument("--start-date", type=str, default="", help="Announcement start date: YYYYMMDD or YYYY-MM-DD")
    parser.add_argument("--end-date", type=str, default="", help="Announcement end date: YYYYMMDD or YYYY-MM-DD")
    parser.add_argument("--last-days", type=int, default=30, help="Pull most recent N calendar days by ann_date")
    parser.add_argument("--ts-codes", type=str, default="", help="Comma-separated stock codes for testing (e.g., '000001.SZ,600000.SH')")
    parser.add_argument("--sleep", type=float, default=0.0, help="Sleep seconds between API calls")
    return parser.parse_args()


def normalize_date(value: str | None) -> str:
    text = str(value or "").strip().replace("-", "")
    if not text:
        return ""
    if len(text) != 8 or not text.isdigit():
        raise ValueError(f"invalid date: {value}")
    return text


def resolve_dates(args: argparse.Namespace) -> tuple[str, str]:
    today = dt.datetime.now().strftime("%Y%m%d")
    end_date = normalize_date(args.end_date) or today
    if args.last_days and args.last_days > 0:
        end_dt = dt.datetime.strptime(end_date, "%Y%m%d")
        start_dt = end_dt - dt.timedelta(days=args.last_days - 1)
        start_date = start_dt.strftime("%Y%m%d")
    else:
        start_date = normalize_date(args.start_date) or end_date
    return start_date, end_date


def get_incremental_targets(start_date: str, end_date: str) -> list[tuple[str, str]]:
    disclosure_glob = settings.data_dir / "raw" / "disclosure_date" / "**" / "*.parquet"
    query = """
        SELECT ts_code, max(end_date) AS period
        FROM read_parquet(?, hive_partitioning=1, union_by_name=true)
        WHERE ts_code IS NOT NULL
          AND end_date IS NOT NULL
          AND (
            ann_date BETWEEN ? AND ?
            OR actual_date BETWEEN ? AND ?
            OR modify_date BETWEEN ? AND ?
          )
        GROUP BY ts_code
        ORDER BY ts_code
    """
    try:
        with get_connection(read_only=True) as conn:
            rows = conn.execute(
                query,
                [
                    str(disclosure_glob),
                    start_date,
                    end_date,
                    start_date,
                    end_date,
                    start_date,
                    end_date,
                ],
            ).fetchall()
    except Exception as exc:
        logger.warning("Failed to load disclosure_date candidates for %s-%s: %s", start_date, end_date, exc)
        return []
    return [(str(row[0]).strip(), str(row[1]).strip()) for row in rows if row and row[0] and row[1]]


def get_ts_codes(args: argparse.Namespace, start_date: str, end_date: str) -> list[str]:
    if args.ts_codes:
        return [code.strip() for code in args.ts_codes.split(",") if code.strip()]
    return list_stock_codes()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    args = parse_args()
    if not settings.tushare_token:
        raise SystemExit("TUSHARE_TOKEN is required")

    start_date, end_date = resolve_dates(args)
    daily_targets = [] if args.ts_codes or args.mode != "daily" else get_incremental_targets(start_date, end_date)
    ts_codes = get_ts_codes(args, start_date, end_date)

    if daily_targets:
        logger.info(
            "sync_fina_audit daily mode: using disclosure_date candidates=%s for %s-%s",
            len(daily_targets),
            start_date,
            end_date,
        )
    elif args.mode == "daily" and not args.ts_codes:
        logger.warning("sync_fina_audit daily mode found no disclosure_date candidates; falling back to full stock list")
    
    target_count = len(daily_targets) if daily_targets else len(ts_codes)
    logger.info("sync_fina_audit: mode=%s, start_date=%s, end_date=%s, stocks=%s", args.mode, start_date, end_date, target_count)
    
    ensure_financial_tables()
    
    total_upserted = 0
    empty_count = 0
    
    targets = daily_targets or [(ts_code, "") for ts_code in ts_codes]
    progress = tqdm(targets, total=len(targets), desc="sync_fina_audit", unit="stock", dynamic_ncols=True)
    for idx, (ts_code, period) in enumerate(progress, start=1):
        try:
            fetch_kwargs = {"ts_code": ts_code}
            if period:
                fetch_kwargs["period"] = period
            else:
                fetch_kwargs["start_date"] = start_date
                fetch_kwargs["end_date"] = end_date
            df = fetch_fina_audit(**fetch_kwargs)
            if df is None or df.empty:
                empty_count += 1
                logger.debug("No fina_audit data for %s in date range %s-%s", ts_code, start_date, end_date)
                continue
            
            # Normalize date columns
            for col in ("ann_date", "end_date"):
                if col in df.columns:
                    df[col] = df[col].map(lambda x: str(x).replace("-", "") if x not in (None, "") else None)
            
            upserted = upsert_fina_audit(df)
            total_upserted += upserted
            
            progress.set_postfix(ts_code=ts_code, upserted=upserted, total=total_upserted)
            
            if args.sleep > 0 and idx < len(targets):
                time.sleep(args.sleep)
                
        except Exception as exc:
            logger.warning("Failed to fetch fina_audit for %s: %s", ts_code, exc)
            continue
    
    # Mark sync done only after all stocks are processed
    mark_sync_done(end_date, "sync_fina_audit")
    
    logger.info(
        "sync_fina_audit done: stocks=%s, empty=%s, total_upserted=%s",
        len(ts_codes),
        empty_count,
        total_upserted,
    )


if __name__ == "__main__":
    main()
