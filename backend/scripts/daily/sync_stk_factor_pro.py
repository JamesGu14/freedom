#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
import time
import uuid
from pathlib import Path

import pandas as pd
from tqdm import tqdm

SCRIPT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(SCRIPT_ROOT))

from app.core.config import settings  # noqa: E402
from app.data.mongo import get_collection  # noqa: E402
from app.data.mongo_data_sync_date import mark_sync_done  # noqa: E402
from app.data.tushare_client import fetch_stk_factor_pro  # noqa: E402

logger = logging.getLogger(__name__)

API_FIELDS = [
    "ts_code",
    "trade_date",
    "close_qfq",
    "ma_qfq_5",
    "ma_qfq_10",
    "ma_qfq_20",
    "ma_qfq_30",
    "ma_qfq_60",
    "ma_qfq_90",
    "ma_qfq_250",
    "macd_dif_qfq",
    "macd_dea_qfq",
    "macd_qfq",
    "kdj_k_qfq",
    "kdj_d_qfq",
    "kdj_qfq",
    "boll_upper_qfq",
    "boll_mid_qfq",
    "boll_lower_qfq",
    "rsi_qfq_6",
    "rsi_qfq_12",
    "rsi_qfq_24",
    "atr_qfq",
    "cci_qfq",
    "wr_qfq",
    "wr1_qfq",
    "updays",
    "downdays",
    "pe",
    "pe_ttm",
    "pb",
    "turnover_rate",
    "turnover_rate_f",
    "volume_ratio",
]
API_FIELDS_CSV = ",".join(API_FIELDS)

RENAME_MAP = {
    "ma_qfq_5": "ma5",
    "ma_qfq_10": "ma10",
    "ma_qfq_20": "ma20",
    "ma_qfq_30": "ma30",
    "ma_qfq_60": "ma60",
    "ma_qfq_90": "ma90",
    "ma_qfq_250": "ma250",
    "macd_dif_qfq": "macd",
    "macd_dea_qfq": "macd_signal",
    "macd_qfq": "macd_hist",
    "kdj_k_qfq": "kdj_k",
    "kdj_d_qfq": "kdj_d",
    "kdj_qfq": "kdj_j",
    "boll_upper_qfq": "boll_upper",
    "boll_mid_qfq": "boll_middle",
    "boll_lower_qfq": "boll_lower",
    "rsi_qfq_6": "rsi6",
    "rsi_qfq_12": "rsi12",
    "rsi_qfq_24": "rsi24",
    "atr_qfq": "atr",
    "cci_qfq": "cci",
    "wr_qfq": "wr",
    "wr1_qfq": "wr1",
}

OUTPUT_COLUMNS = [
    "ts_code",
    "trade_date",
    "close_qfq",
    "ma5",
    "ma10",
    "ma20",
    "ma30",
    "ma60",
    "ma90",
    "ma250",
    "macd",
    "macd_signal",
    "macd_hist",
    "kdj_k",
    "kdj_d",
    "kdj_j",
    "boll_upper",
    "boll_middle",
    "boll_lower",
    "rsi6",
    "rsi12",
    "rsi24",
    "atr",
    "cci",
    "wr",
    "wr1",
    "updays",
    "downdays",
    "pe",
    "pe_ttm",
    "pb",
    "turnover_rate",
    "turnover_rate_f",
    "volume_ratio",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync stock technical indicators from TuShare stk_factor_pro into parquet partitions."
    )
    parser.add_argument("--trade-date", type=str, default="", help="Single trade date: YYYYMMDD or YYYY-MM-DD")
    parser.add_argument("--start-date", type=str, default="", help="Start date: YYYYMMDD or YYYY-MM-DD")
    parser.add_argument("--end-date", type=str, default="", help="End date: YYYYMMDD or YYYY-MM-DD")
    parser.add_argument(
        "--last-days",
        type=int,
        default=0,
        help="Pull most recent N calendar days (auto skip non-trading days)",
    )
    parser.add_argument("--sleep", type=float, default=2.0, help="Sleep seconds between API calls")
    return parser.parse_args()


def normalize_date(value: str | None) -> str:
    if not value:
        return ""
    text = str(value).strip().replace("-", "")
    if len(text) != 8 or not text.isdigit():
        raise ValueError(f"invalid date: {value}")
    return text


def build_date_list(start_date: str, end_date: str) -> list[str]:
    start = dt.datetime.strptime(start_date, "%Y%m%d")
    end = dt.datetime.strptime(end_date, "%Y%m%d")
    if start > end:
        raise ValueError("start-date cannot be later than end-date")
    return [d.strftime("%Y%m%d") for d in pd.date_range(start, end)]


def resolve_dates(args: argparse.Namespace) -> list[str]:
    if args.trade_date and (args.start_date or args.end_date or args.last_days):
        raise ValueError("--trade-date cannot be used with --start-date/--end-date/--last-days")

    today = dt.datetime.now().strftime("%Y%m%d")
    end_date = normalize_date(args.end_date) or today

    if args.trade_date:
        return [normalize_date(args.trade_date)]

    if args.last_days and args.last_days > 0:
        end_dt = dt.datetime.strptime(end_date, "%Y%m%d")
        start_dt = end_dt - dt.timedelta(days=args.last_days - 1)
        start_date = start_dt.strftime("%Y%m%d")
    else:
        start_date = normalize_date(args.start_date) or end_date

    return build_date_list(start_date, end_date)


def load_open_dates(start_date: str, end_date: str, exchange: str = "SSE") -> set[str]:
    collection = get_collection("trade_calendar")
    cursor = collection.find(
        {
            "exchange": exchange,
            "cal_date": {"$gte": start_date, "$lte": end_date},
            "is_open": {"$in": ["1", 1]},
        },
        {"_id": 0, "cal_date": 1},
    )
    dates = {str(doc.get("cal_date")) for doc in cursor if doc.get("cal_date")}
    if not dates:
        logger.warning(
            "trade_calendar has no open dates in range [%s, %s], all days will be skipped",
            start_date,
            end_date,
        )
    return dates


def normalize_trade_date(value: object, default_date: str) -> str:
    text = str(value or "").strip().replace("-", "")
    if len(text) == 8 and text.isdigit():
        return text
    return default_date


def transform_indicator_df(df: pd.DataFrame, trade_date: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    data = df.copy()
    if "trade_date" not in data.columns:
        data["trade_date"] = trade_date

    available_columns = [col for col in API_FIELDS if col in data.columns]
    if "ts_code" not in available_columns:
        return pd.DataFrame()

    data = data[available_columns].rename(columns=RENAME_MAP)
    data["trade_date"] = data["trade_date"].apply(lambda x: normalize_trade_date(x, trade_date))

    for col in OUTPUT_COLUMNS:
        if col not in data.columns:
            data[col] = None

    data = data[OUTPUT_COLUMNS].drop_duplicates(subset=["ts_code", "trade_date"], keep="last")
    return data


def save_indicators(df: pd.DataFrame) -> int:
    if df is None or df.empty:
        return 0

    features_base = settings.data_dir / "features" / "indicators"
    features_base.mkdir(parents=True, exist_ok=True)

    data = df.copy()
    data["trade_date"] = data["trade_date"].astype(str).str.replace("-", "", regex=False)
    data["year"] = data["trade_date"].str[:4]

    saved = 0
    for (ts_code, year), group in data.groupby(["ts_code", "year"], sort=False):
        partition_dir = features_base / f"ts_code={ts_code}" / f"year={year}"
        partition_dir.mkdir(parents=True, exist_ok=True)
        part_path = partition_dir / f"part-{uuid.uuid4().hex}.parquet"
        new_rows = group.drop(columns=["year"])
        new_rows.to_parquet(part_path, index=False, engine="pyarrow")
        saved += len(new_rows)
    return saved


def flush_year_buffer(year: str, frames: list[pd.DataFrame]) -> tuple[int, int]:
    if not frames:
        return 0, 0
    year_df = pd.concat(frames, ignore_index=True)
    year_df = year_df.drop_duplicates(subset=["ts_code", "trade_date"], keep="last")
    saved = save_indicators(year_df)
    logger.info(
        "flush year=%s rows=%s saved=%s stocks=%s",
        year,
        len(year_df),
        saved,
        year_df["ts_code"].nunique(),
    )
    return saved, len(year_df)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    args = parse_args()
    if not settings.tushare_token:
        raise SystemExit("TUSHARE_TOKEN is required")

    date_list = resolve_dates(args)
    if not date_list:
        logger.info("no dates to sync")
        return

    start_date = min(date_list)
    end_date = max(date_list)
    open_dates = load_open_dates(start_date, end_date)

    logger.info(
        "sync_stk_factor_pro start: start=%s end=%s days=%s sleep=%.2f",
        start_date,
        end_date,
        len(date_list),
        args.sleep,
    )

    total_saved = 0
    total_buffered = 0
    total_api_rows = 0
    synced_days = 0
    synced_dates: list[str] = []
    current_year = ""
    year_frames: list[pd.DataFrame] = []

    skipped_non_trading = 0
    progress = tqdm(date_list, total=len(date_list), desc="sync_stk_factor_pro", unit="day", dynamic_ncols=True)
    for idx, trade_date in enumerate(progress, start=1):
        if trade_date not in open_dates:
            skipped_non_trading += 1
            progress.set_postfix(date=trade_date, status="skip")
            continue

        try:
            raw_df = fetch_stk_factor_pro(trade_date=trade_date, fields=API_FIELDS_CSV)
            api_rows = 0 if raw_df is None else len(raw_df)
            total_api_rows += api_rows
            if raw_df is None or raw_df.empty:
                progress.set_postfix(date=trade_date, status="no_data")
            else:
                normalized_df = transform_indicator_df(raw_df, trade_date)
                if normalized_df.empty:
                    progress.set_postfix(date=trade_date, status="empty_after_transform")
                    continue
                trade_year = trade_date[:4]
                if not current_year:
                    current_year = trade_year
                if trade_year != current_year:
                    saved, buffered = flush_year_buffer(current_year, year_frames)
                    total_saved += saved
                    total_buffered += buffered
                    year_frames = []
                    current_year = trade_year

                year_frames.append(normalized_df)
                synced_days += 1
                synced_dates.append(trade_date)
                progress.set_postfix(
                    date=trade_date,
                    api_rows=api_rows,
                    buffered=len(normalized_df),
                    stocks=normalized_df["ts_code"].nunique(),
                )
        except Exception as exc:
            logger.exception("[%s/%s] %s failed: %s", idx, len(date_list), trade_date, exc)

        if args.sleep > 0 and idx < len(date_list):
            time.sleep(args.sleep)

    if year_frames and current_year:
        saved, buffered = flush_year_buffer(current_year, year_frames)
        total_saved += saved
        total_buffered += buffered

    for d in synced_dates:
        mark_sync_done(d, "sync_stk_factor_pro")
    logger.info(
        "sync_stk_factor_pro done: synced_days=%s skipped_non_trading=%s api_rows=%s buffered_rows=%s saved_rows=%s",
        synced_days,
        skipped_non_trading,
        total_api_rows,
        total_buffered,
        total_saved,
    )


if __name__ == "__main__":
    main()
