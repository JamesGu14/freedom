#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import time
from pathlib import Path
import sys

import pandas as pd
import tushare as ts

SCRIPT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(SCRIPT_ROOT))

# 需要在 sys.path 修改后导入
from app.core.config import settings  # noqa: E402
from app.data.tushare_client import fetch_stock_basic  # noqa: E402
from app.data.duckdb_store import (  # noqa: E402
    get_connection,
    replace_stock_basic,
    upsert_adj_factor,
    upsert_daily,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Pull daily and adj_factor history from TuShare "
            "and store in DuckDB."
        )
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default="",
        help="YYYYMMDD, override start date",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default="",
        help="YYYYMMDD, override end date",
    )
    parser.add_argument(
        "--sleep", type=float, default=0.3, help="Sleep seconds between calls"
    )
    return parser.parse_args()


def normalize_date(value: str | None) -> str:
    if value:
        return value
    return dt.datetime.now().strftime("%Y%m%d")


def ensure_stock_basic() -> None:
    max_retries = 3
    for attempt in range(max_retries):
        try:
            with get_connection() as con:
                try:
                    existing = con.execute(
                        "SELECT COUNT(*) FROM stock_basic").fetchone()[0]
                except Exception:
                    existing = 0
            if existing:
                return

            df = fetch_stock_basic()
            replace_stock_basic(df)
            return
        except Exception as exc:
            if attempt < max_retries - 1:
                time.sleep(0.5 * (attempt + 1))
                continue
            raise SystemExit(
                f"Failed to ensure stock_basic after {max_retries} "
                f"attempts: {exc}"
            )


def load_stock_list() -> list[tuple[str, str]]:
    max_retries = 3
    for attempt in range(max_retries):
        try:
            with get_connection() as con:
                rows = con.execute(
                    "SELECT ts_code, list_date FROM stock_basic").fetchall()
            return [(row[0], row[1]) for row in rows]
        except Exception as exc:
            if attempt < max_retries - 1:
                time.sleep(0.5 * (attempt + 1))
                continue
            raise SystemExit(
                f"Failed to load stock list after {max_retries} "
                f"attempts: {exc}"
            )
    return []


def check_stock_data_exists(
    ts_code: str,
    start_date: str,
    end_date: str,
    max_retries: int = 3,
) -> tuple[bool, str | None]:
    """
    检查股票数据是否已存在且完整覆盖请求的日期范围。
    返回: (是否需要拉取, 实际需要拉取的开始日期)
    """
    for attempt in range(max_retries):
        try:
            with get_connection() as con:
                # 检查表是否存在
                try:
                    con.execute("SELECT 1 FROM daily LIMIT 1")
                except Exception:
                    return True, None  # 表不存在，需要拉取

                # 检查是否有数据
                count_result = con.execute(
                    "SELECT COUNT(*) FROM daily WHERE ts_code = ?", [ts_code]
                ).fetchone()
                if count_result is None or count_result[0] == 0:
                    return True, None  # 没有数据，需要拉取

                return False, None
        except Exception as exc:
            if attempt < max_retries - 1:
                # 重试前等待
                time.sleep(0.5 * (attempt + 1))
                continue
            # 最后一次尝试失败，记录错误但返回需要拉取（保守策略）
            print(
                f"WARNING: Failed to check data for {ts_code} "
                f"after {max_retries} attempts: {exc}. "
                f"Will pull data."
            )
            return True, None
    return True, None


def pull_history(
    pro: ts.pro_api, ts_code: str, start_date: str, end_date: str
) -> tuple[pd.DataFrame, pd.DataFrame]:
    daily_df = pro.daily(
        ts_code=ts_code, start_date=start_date, end_date=end_date)
    adj_df = pro.adj_factor(
        ts_code=ts_code, start_date=start_date, end_date=end_date)
    return daily_df, adj_df


def main() -> None:
    args = parse_args()

    end_date = normalize_date(args.end_date)
    override_start = args.start_date or ""

    # 确保 TUSHARE_TOKEN 已设置
    if not settings.tushare_token:
        # 如果环境变量未设置，使用硬编码的 token（仅用于开发）
        import os
        default_token = (
            "e14d179a9b5acda0028ea672ecb535d9541402ba5e15e31687a4439e"
        )
        token = os.getenv("TUSHARE_TOKEN", default_token)
        settings.tushare_token = token

    ensure_stock_basic()
    stock_list = load_stock_list()
    if not stock_list:
        raise SystemExit("No stock_basic data available")

    pro = ts.pro_api(settings.tushare_token)

    for idx, (ts_code, list_date) in enumerate(stock_list, start=1):
        start_date = override_start or list_date

        # 检查数据是否已存在
        need_pull, actual_start = check_stock_data_exists(
            ts_code, start_date, end_date)

        if not need_pull:
            print(
                f"[{idx}/{len(stock_list)}] {ts_code} {start_date}-{end_date} "
                f"SKIPPED (data already exists)"
            )
            continue

        # 使用实际需要拉取的开始日期
        pull_start = actual_start if actual_start else start_date

        try:
            daily_df, adj_df = pull_history(pro, ts_code, pull_start, end_date)

            # 写入数据时也添加重试机制
            max_write_retries = 3
            inserted_daily = 0
            inserted_adj = 0
            for write_attempt in range(max_write_retries):
                try:
                    inserted_daily = upsert_daily(daily_df)
                    inserted_adj = upsert_adj_factor(adj_df)
                    break
                except Exception as write_exc:
                    if write_attempt < max_write_retries - 1:
                        time.sleep(0.5 * (write_attempt + 1))
                        continue
                    print(
                        f"[{idx}/{len(stock_list)}] {ts_code} "
                        f"write failed after {max_write_retries} attempts: "
                        f"{write_exc}"
                    )
                    raise

            status = "UPDATED" if actual_start else "NEW"
            print(
                f"[{idx}/{len(stock_list)}] {ts_code} {pull_start}-{end_date} "
                f"daily={inserted_daily} adj_factor={inserted_adj} [{status}]"
            )
        except Exception as exc:
            print(f"[{idx}/{len(stock_list)}] {ts_code} failed: {exc}")
        time.sleep(args.sleep)


if __name__ == "__main__":
    main()
