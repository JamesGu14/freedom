#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
import time
from pathlib import Path

import pandas as pd
from tqdm import tqdm

SCRIPT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(SCRIPT_ROOT))

from app.core.config import settings  # noqa: E402
from app.data.mongo_data_sync_date import mark_sync_done  # noqa: E402
from app.data.mongo_shenwan import list_shenwan_industry  # noqa: E402
from app.data.mongo_shenwan_daily import upsert_shenwan_daily  # noqa: E402
from app.data.mongo_trade_calendar import is_trading_day  # noqa: E402
from app.data.tushare_client import fetch_shenwan_daily  # noqa: E402

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync Shenwan daily index data from TuShare into MongoDB."
    )
    parser.add_argument("--trade-date", type=str, default="", help="YYYYMMDD trade date")
    parser.add_argument("--start-date", type=str, default="", help="YYYYMMDD, override start date")
    parser.add_argument("--end-date", type=str, default="", help="YYYYMMDD, override end date")
    parser.add_argument(
        "--last-days",
        type=int,
        default=0,
        help="Pull the most recent N days (optionally ending at --end-date)",
    )
    parser.add_argument("--sleep", type=float, default=0, help="Sleep seconds between calls")
    return parser.parse_args()


def normalize_date(value: str | None) -> str:
    if value:
        return value
    return dt.datetime.now().strftime("%Y%m%d")


def build_date_list(start_date: str, end_date: str) -> list[str]:
    start = dt.datetime.strptime(start_date, "%Y%m%d")
    end = dt.datetime.strptime(end_date, "%Y%m%d")
    return [d.strftime("%Y%m%d") for d in pd.date_range(start, end)]


def _build_level_map(version: str = "2021") -> dict[str, int]:
    items = list_shenwan_industry(version=version)
    result: dict[str, int] = {}
    for item in items:
        index_code = item.get("index_code")
        level = item.get("level")
        if not index_code or level is None:
            continue
        result[str(index_code)] = int(level)
    return result


def _apply_ranks(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["rank"] = None
    df["rank_total"] = None

    for level in [1, 2, 3]:
        mask = df["level"] == level
        level_df = df[mask].copy()
        if level_df.empty:
            continue
        level_df["rank"] = level_df["pct_change"].rank(
            ascending=False, method="min"
        )
        df.loc[mask, "rank"] = level_df["rank"].astype("Int64")
        df.loc[mask, "rank_total"] = len(level_df)
    return df


def _to_records(df: pd.DataFrame) -> list[dict[str, object]]:
    if df is None or df.empty:
        return []
    normalized = df.where(pd.notna(df), None)
    return normalized.to_dict(orient="records")


def _pick_fields(row: dict[str, object]) -> dict[str, object]:
    return {
        "ts_code": row.get("ts_code"),
        "trade_date": row.get("trade_date"),
        "name": row.get("name"),
        "open": row.get("open"),
        "high": row.get("high"),
        "low": row.get("low"),
        "close": row.get("close"),
        "change": row.get("change"),
        "pct_change": row.get("pct_change"),
        "vol": row.get("vol"),
        "amount": row.get("amount"),
        "pe": row.get("pe"),
        "pb": row.get("pb"),
        "float_mv": row.get("float_mv"),
        "total_mv": row.get("total_mv"),
        "level": row.get("level"),
        "rank": row.get("rank"),
        "rank_total": row.get("rank_total"),
    }


def sync_trade_date(trade_date: str, level_map: dict[str, int]) -> int:
    df = fetch_shenwan_daily(trade_date=trade_date)
    if df is None or df.empty:
        logger.debug("%s no shenwan daily data returned", trade_date)
        return 0

    df["trade_date"] = df.get("trade_date", trade_date)
    df["pct_change"] = pd.to_numeric(df.get("pct_change"), errors="coerce")
    df["level"] = df["ts_code"].map(level_map)
    df = _apply_ranks(df)

    rows = _to_records(df)
    records = []
    for row in rows:
        record = _pick_fields(row)
        level = record.get("level")
        if level is not None:
            try:
                record["level"] = int(level)
            except (TypeError, ValueError):
                record["level"] = None
        records.append(record)

    inserted = upsert_shenwan_daily(records)
    logger.debug("%s upserted %s records", trade_date, inserted)
    return inserted


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    args = parse_args()
    if not settings.tushare_token:
        raise SystemExit("TUSHARE_TOKEN is required")

    end_date = normalize_date(args.end_date)
    if args.trade_date:
        date_list = [args.trade_date]
    elif args.last_days and args.last_days > 0:
        end_dt = dt.datetime.strptime(end_date, "%Y%m%d")
        start_dt = end_dt - dt.timedelta(days=args.last_days - 1)
        start_date = start_dt.strftime("%Y%m%d")
        date_list = build_date_list(start_date, end_date)
    else:
        start_date = normalize_date(args.start_date) if args.start_date else end_date
        date_list = build_date_list(start_date, end_date)

    level_map = _build_level_map()
    if not level_map:
        logger.warning("shenwan_industry level map is empty")

    total_upserted = 0
    skipped_non_trading = 0
    synced_dates: list[str] = []
    progress = tqdm(date_list, total=len(date_list), desc="sync_shenwan_daily", unit="day", dynamic_ncols=True)
    for idx, trade_date in enumerate(progress, start=1):
        try:
            if not is_trading_day(trade_date):
                skipped_non_trading += 1
                progress.set_postfix(date=trade_date, status="skip")
                continue
            inserted = sync_trade_date(trade_date, level_map)
            total_upserted += inserted
            if inserted > 0:
                synced_dates.append(trade_date)
            progress.set_postfix(date=trade_date, upserted=inserted, total=total_upserted)
        except Exception as exc:
            logger.exception("[%s/%s] %s failed: %s", idx, len(date_list), trade_date, exc)
        if args.sleep > 0:
            time.sleep(args.sleep)

    for d in synced_dates:
        mark_sync_done(d, "sync_shenwan_daily")
    logger.info(
        "sync_shenwan_daily done: days=%s skipped_non_trading=%s upserted=%s",
        len(date_list),
        skipped_non_trading,
        total_upserted,
    )


if __name__ == "__main__":
    main()
