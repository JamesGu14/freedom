#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
import time
from collections import defaultdict
from pathlib import Path

import pandas as pd
from tqdm import tqdm

SCRIPT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(SCRIPT_ROOT))

from app.core.config import settings  # noqa: E402
from app.data.mongo import get_collection  # noqa: E402
from app.data.mongo_data_sync_date import mark_sync_done  # noqa: E402
from app.data.mongo_citic import (  # noqa: E402
    list_citic_industry,
    upsert_citic_industry,
    upsert_citic_members,
)
from app.data.mongo_citic_daily import upsert_citic_daily  # noqa: E402
from app.data.mongo_market_index import (  # noqa: E402
    DEFAULT_MARKET_INDEX_CODES,
    upsert_index_factor_pro,
    upsert_market_index_dailybasic,
)
from app.data.mongo_shenwan import list_shenwan_industry  # noqa: E402
from app.data.tushare_client import (  # noqa: E402
    fetch_citic_daily,
    fetch_citic_members,
    fetch_idx_factor_pro,
    fetch_index_dailybasic,
)

FACTOR_PAGE_SIZE = 8000
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync citic sector/index data and market index metrics from TuShare."
    )
    parser.add_argument("--start-date", type=str, default="", help="YYYYMMDD start date")
    parser.add_argument("--end-date", type=str, default="", help="YYYYMMDD end date")
    parser.add_argument(
        "--full-history",
        action="store_true",
        help="Pull full history from --history-start-date to --end-date",
    )
    parser.add_argument(
        "--history-start-date",
        type=str,
        default="20050101",
        help="History pull start date in YYYYMMDD",
    )
    parser.add_argument(
        "--modules",
        type=str,
        default="all",
        choices=["all", "citic", "market", "sw"],
        help="all/citic/market/sw(sw=only shenwan factors)",
    )
    parser.add_argument(
        "--index-codes",
        type=str,
        default=",".join(DEFAULT_MARKET_INDEX_CODES),
        help="Market index codes separated by comma",
    )
    parser.add_argument(
        "--skip-members",
        action="store_true",
        help="Skip citic member/industry sync for faster reruns",
    )
    parser.add_argument(
        "--skip-factors",
        action="store_true",
        help="Skip idx_factor_pro sync for faster runs",
    )
    parser.add_argument("--sleep", type=float, default=0.2, help="Sleep seconds between API calls")
    return parser.parse_args()


def normalize_date(value: str | None) -> str:
    if not value:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    text = text.replace("-", "")
    if len(text) != 8 or not text.isdigit():
        raise ValueError(f"invalid date: {value}")
    return text


def normalize_compose_date(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None
    text = text.replace("-", "")
    if len(text) == 8 and text.isdigit():
        return text
    return text


def build_date_list(start_date: str, end_date: str) -> list[str]:
    start = dt.datetime.strptime(start_date, "%Y%m%d")
    end = dt.datetime.strptime(end_date, "%Y%m%d")
    if start > end:
        raise ValueError("start-date cannot be later than end-date")
    return [d.strftime("%Y%m%d") for d in pd.date_range(start, end)]


def to_records(df: pd.DataFrame) -> list[dict[str, object]]:
    if df is None or df.empty:
        return []
    normalized = df.where(pd.notna(df), None)
    return normalized.to_dict(orient="records")


def parse_level(level_raw: object) -> int | None:
    text = str(level_raw or "").strip().upper()
    if text in {"1", "L1", "一级行业", "一级"}:
        return 1
    if text in {"2", "L2", "二级行业", "二级"}:
        return 2
    if text in {"3", "L3", "三级行业", "三级"}:
        return 3
    return None


def normalize_index_code(code: object, source: str) -> str | None:
    if code is None:
        return None
    text = str(code).strip().upper()
    if not text:
        return None
    if "." in text:
        return text
    if source == "sw":
        return f"{text}.SI"
    if source == "ci":
        return f"{text}.CI"
    if source == "market":
        if text.startswith("399"):
            return f"{text}.SZ"
        return f"{text}.SH"
    return text


def normalize_index_root(code: object) -> str | None:
    if code is None:
        return None
    text = str(code).strip().upper()
    if not text:
        return None
    return text.split(".", 1)[0]


def build_index_code_aliases(code: object, source: str) -> list[str]:
    root = normalize_index_root(code)
    if not root:
        return []
    aliases = [root]
    if source == "ci":
        aliases.extend([f"{root}.WI", f"{root}.CI"])
    elif source == "sw":
        aliases.append(f"{root}.SI")
    elif source == "market":
        aliases.extend([f"{root}.SH", f"{root}.SZ"])
    canonical = normalize_index_code(code, source)
    if canonical:
        aliases.append(canonical)
    return list(dict.fromkeys(aliases))


def is_sync_date(date_value: str, exchange: str = "SSE") -> bool:
    """Only sync on trading day records explicitly marked open in trade_calendar."""
    collection = get_collection("trade_calendar")
    doc = collection.find_one(
        {"exchange": exchange, "cal_date": date_value},
        {"_id": 0, "is_open": 1},
    )
    if doc is None:
        return False
    return str(doc.get("is_open")) == "1"


def parse_index_codes(value: str) -> list[str]:
    parts = [item.strip() for item in str(value or "").split(",")]
    codes: list[str] = []
    for item in parts:
        if not item:
            continue
        code = normalize_index_code(item, "market")
        if code:
            codes.append(code)
    return list(dict.fromkeys(codes))


def apply_rank(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    ranked = df.copy()
    ranked["rank"] = None
    ranked["rank_total"] = None
    ranked["pct_change"] = pd.to_numeric(ranked.get("pct_change"), errors="coerce")
    for level in [1, 2, 3]:
        mask = ranked["level"] == level
        level_df = ranked[mask].copy()
        if level_df.empty:
            continue
        level_df["rank"] = level_df["pct_change"].rank(ascending=False, method="min")
        ranked.loc[mask, "rank"] = level_df["rank"].astype("Int64")
        ranked.loc[mask, "rank_total"] = len(level_df)
    return ranked


def sync_citic_members(*, sleep_seconds: float) -> tuple[int, int]:
    all_member_records: list[dict[str, object]] = []
    industry_map: dict[str, dict[str, object]] = {}
    member_codes_by_index: dict[str, set[str]] = defaultdict(set)

    df = fetch_citic_members(is_new="Y")
    rows = to_records(df)
    if not rows:
        df = fetch_citic_members()
        rows = to_records(df)
        logger.info("citic members fallback(all) rows=%s", len(rows))
    else:
        logger.info("citic members latest rows=%s", len(rows))

    for row in rows:
        l1_code = normalize_index_code(row.get("l1_code"), "ci")
        l2_code = normalize_index_code(row.get("l2_code"), "ci")
        l3_code = normalize_index_code(row.get("l3_code"), "ci")
        l1_name = row.get("l1_name")
        l2_name = row.get("l2_name")
        l3_name = row.get("l3_name")

        for code, name, level in [
            (l1_code, l1_name, 1),
            (l2_code, l2_name, 2),
            (l3_code, l3_name, 3),
        ]:
            if not code:
                continue
            if code not in industry_map:
                industry_map[code] = {
                    "index_code": code,
                    "industry_code": normalize_index_root(code),
                    "industry_name": name,
                    "level": level,
                    "level_raw": f"L{level}",
                    "source": "citic",
                }
            elif not industry_map[code].get("industry_name") and name:
                industry_map[code]["industry_name"] = name

        cons_code = row.get("ts_code")
        in_date = normalize_compose_date(row.get("in_date"))
        if not cons_code or not l3_code or not in_date:
            continue

        member_record = {
            "index_code": l3_code,
            "industry_code": normalize_index_root(l3_code),
            "industry_name": l3_name,
            "level": 3,
            "level_raw": "L3",
            "cons_code": cons_code,
            "cons_ticker": str(cons_code).split(".", 1)[0],
            "cons_name": row.get("name"),
            "in_date": in_date,
            "out_date": normalize_compose_date(row.get("out_date")),
            "is_new": str(row.get("is_new") or "Y").upper(),
        }
        all_member_records.append(member_record)
        member_codes_by_index[l3_code].add(str(cons_code))

    if sleep_seconds > 0:
        time.sleep(sleep_seconds)

    for index_code, item in industry_map.items():
        item["member_count_latest"] = len(member_codes_by_index.get(index_code, set()))
        item["is_active"] = item["member_count_latest"] > 0

    member_count = upsert_citic_members(all_member_records)
    industry_count = upsert_citic_industry(list(industry_map.values()))
    logger.info(
        "citic members upserted=%s industries upserted=%s",
        member_count,
        industry_count,
    )
    return member_count, industry_count


def build_citic_maps() -> tuple[dict[str, int], dict[str, str]]:
    items = list_citic_industry()
    level_map: dict[str, int] = {}
    name_map: dict[str, str] = {}
    for item in items:
        index_code = str(item.get("index_code") or "").strip().upper()
        level = item.get("level")
        if not index_code:
            continue
        aliases = build_index_code_aliases(index_code, "ci")
        if isinstance(level, int):
            for alias in aliases:
                level_map[alias] = level
        name = item.get("industry_name")
        if name:
            for alias in aliases:
                name_map[alias] = str(name)
    return level_map, name_map


def sync_citic_daily_for_date(
    trade_date: str,
    *,
    level_map: dict[str, int],
    name_map: dict[str, str],
    verbose: bool = True,
) -> int:
    df = fetch_citic_daily(trade_date=trade_date)
    if df is None or df.empty:
        if verbose:
            logger.info("%s citic_daily no data", trade_date)
        return 0

    df = df.copy()
    if "ts_code" not in df.columns and "index_code" in df.columns:
        df["ts_code"] = df.get("index_code")
    df["trade_date"] = df.get("trade_date", trade_date)
    df["ts_code_raw"] = df.get("ts_code")
    df["ts_code"] = df["ts_code_raw"].apply(lambda x: normalize_index_code(x, "ci"))
    df["index_root"] = df["ts_code_raw"].apply(normalize_index_root)
    df["level"] = df["ts_code"].map(level_map)
    df["name"] = df["ts_code"].map(name_map)
    root_level = df["index_root"].map(level_map)
    root_name = df["index_root"].map(name_map)
    df["level"] = df["level"].fillna(root_level)
    df["name"] = df["name"].fillna(root_name)
    if "industry_name" in df.columns:
        df["name"] = df["name"].fillna(df.get("industry_name"))
    df = apply_rank(df)

    rows = to_records(df)
    records: list[dict[str, object]] = []
    for row in rows:
        records.append(
            {
                "ts_code": row.get("ts_code"),
                "trade_date": row.get("trade_date"),
                "name": row.get("name"),
                "level": row.get("level"),
                "open": row.get("open"),
                "high": row.get("high"),
                "low": row.get("low"),
                "close": row.get("close"),
                "change": row.get("change"),
                "pct_change": row.get("pct_change"),
                "vol": row.get("vol"),
                "amount": row.get("amount"),
                "rank": row.get("rank"),
                "rank_total": row.get("rank_total"),
            }
        )

    upserted = upsert_citic_daily(records)
    if verbose:
        logger.info("%s citic_daily upserted=%s", trade_date, upserted)
    return upserted


def _build_market_dailybasic_records(df: pd.DataFrame) -> list[dict[str, object]]:
    rows = to_records(df)
    records: list[dict[str, object]] = []
    for row in rows:
        records.append(
            {
                "ts_code": normalize_index_code(row.get("ts_code"), "market"),
                "trade_date": row.get("trade_date"),
                "total_mv": row.get("total_mv"),
                "float_mv": row.get("float_mv"),
                "total_share": row.get("total_share"),
                "float_share": row.get("float_share"),
                "free_share": row.get("free_share"),
                "turnover_rate": row.get("turnover_rate"),
                "turnover_rate_f": row.get("turnover_rate_f"),
                "total_pe": row.get("total_pe"),
                "pe": row.get("pe"),
                "pb": row.get("pb"),
            }
        )
    return records


def sync_market_dailybasic_for_date(
    *,
    trade_date: str,
    index_codes: list[str],
) -> int:
    # Fetch all indices for the trade_date in a single API call
    df = fetch_index_dailybasic(trade_date=trade_date)
    if df is None or df.empty:
        return 0

    # Filter to only target index codes
    if index_codes:
        index_codes_set = set(index_codes)
        df = df[df["ts_code"].isin(index_codes_set)]

    records = _build_market_dailybasic_records(df)
    return upsert_market_index_dailybasic(records)


def sync_market_dailybasic(
    *,
    start_date: str,
    end_date: str,
    index_codes: list[str],
    sleep_seconds: float,
) -> int:
    total = 0
    for idx, ts_code in enumerate(index_codes, start=1):
        df = fetch_index_dailybasic(
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
        )
        records = _build_market_dailybasic_records(df)
        upserted = upsert_market_index_dailybasic(records)
        total += upserted
        logger.info("market_dailybasic [%s/%s] %s upserted=%s", idx, len(index_codes), ts_code, upserted)
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)
    return total


def detect_factor_source(ts_code: str) -> str | None:
    code = str(ts_code or "").upper()
    if code.endswith(".CI"):
        return "ci"
    if code.endswith(".SI"):
        return "sw"
    if code.endswith(".SH") or code.endswith(".SZ"):
        return "market"
    return None


def sync_index_factors_by_trade_date(
    *,
    trade_dates: list[str],
    target_codes_by_source: dict[str, set[str]],
    sleep_seconds: float,
) -> int:
    total = 0
    progress = tqdm(trade_dates, total=len(trade_dates), desc="sync_index_factors", unit="day", dynamic_ncols=True)
    for idx, trade_date in enumerate(progress, start=1):
        if not is_sync_date(trade_date):
            progress.set_postfix(date=trade_date, status="skip")
            continue

        try:
            day_records: list[dict[str, object]] = []
            day_counts: dict[str, int] = {"market": 0, "sw": 0, "ci": 0}
            offset = 0
            while True:
                df = fetch_idx_factor_pro(
                    trade_date=trade_date,
                    limit=FACTOR_PAGE_SIZE,
                    offset=offset,
                )
                rows = to_records(df)
                if not rows:
                    break

                for row in rows:
                    raw_code = row.get("ts_code")
                    source = detect_factor_source(str(raw_code or ""))
                    if not source:
                        continue
                    if source not in target_codes_by_source:
                        continue
                    normalized_code = normalize_index_code(raw_code, source)
                    if not normalized_code:
                        continue
                    target_codes = target_codes_by_source.get(source)
                    # Empty set means "all indices in this source".
                    if target_codes is None:
                        continue
                    if target_codes and normalized_code not in target_codes:
                        continue

                    record = dict(row)
                    record["ts_code"] = normalized_code
                    record["source"] = source
                    day_records.append(record)
                    day_counts[source] = day_counts.get(source, 0) + 1

                if len(rows) < FACTOR_PAGE_SIZE:
                    break
                offset += len(rows)
                if sleep_seconds > 0:
                    time.sleep(sleep_seconds)

            upserted = upsert_index_factor_pro(day_records)
            total += upserted
            progress.set_postfix(
                date=trade_date,
                fetched=len(day_records),
                market=day_counts.get("market", 0),
                sw=day_counts.get("sw", 0),
                ci=day_counts.get("ci", 0),
                upserted=upserted,
            )
        except Exception as exc:
            logger.exception("factor [%s/%s] %s failed: %s", idx, len(trade_dates), trade_date, exc)
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)
    return total


def sync_index_factors_for_trade_date(
    *,
    trade_date: str,
    target_codes_by_source: dict[str, set[str]],
    sleep_seconds: float,
) -> tuple[int, dict[str, int]]:
    day_records: list[dict[str, object]] = []
    day_counts: dict[str, int] = {"market": 0, "sw": 0, "ci": 0}
    # TuShare idx_factor_pro docs (doc_id=358): single call max 8000 rows.
    # A single trade_date payload is below this cap for market+sw+ci, so call once per day.
    df = fetch_idx_factor_pro(trade_date=trade_date)
    rows = to_records(df)

    for row in rows:
        raw_code = row.get("ts_code")
        source = detect_factor_source(str(raw_code or ""))
        if not source:
            continue
        if source not in target_codes_by_source:
            continue

        normalized_code = normalize_index_code(raw_code, source)
        if not normalized_code:
            continue

        target_codes = target_codes_by_source.get(source)
        # Empty set means "all indices in this source".
        if target_codes is None:
            continue
        if target_codes and normalized_code not in target_codes:
            continue

        record = dict(row)
        record["ts_code"] = normalized_code
        record["source"] = source
        day_records.append(record)
        day_counts[source] = day_counts.get(source, 0) + 1

    upserted = upsert_index_factor_pro(day_records)
    return upserted, day_counts


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    args = parse_args()
    if not settings.tushare_token:
        raise SystemExit("TUSHARE_TOKEN is required")

    today = dt.datetime.now().strftime("%Y%m%d")
    end_date = normalize_date(args.end_date) if args.end_date else today
    if args.full_history:
        start_date = normalize_date(args.history_start_date)
    else:
        start_date = normalize_date(args.start_date) if args.start_date else end_date
    date_list = build_date_list(start_date, end_date)
    index_codes = parse_index_codes(args.index_codes)
    if not index_codes:
        index_codes = list(DEFAULT_MARKET_INDEX_CODES)

    do_citic = args.modules in {"all", "citic"}
    do_market = args.modules in {"all", "market"}
    do_sw_factor = args.modules in {"all", "sw"}

    script_start = time.time()
    logger.info(
        "sync_zhishu_data start: modules=%s start=%s end=%s days=%s",
        args.modules,
        start_date,
        end_date,
        len(date_list),
    )

    level_map: dict[str, int] = {}
    name_map: dict[str, str] = {}
    if do_citic:
        if args.skip_members:
            logger.info("skip citic members/industry sync")
        else:
            try:
                sync_citic_members(sleep_seconds=args.sleep)
            except Exception as exc:
                logger.warning(
                    "citic members/industry sync failed, continue with existing citic_industry data: %s",
                    exc,
                )
        level_map, name_map = build_citic_maps()
        if not level_map:
            logger.warning("citic_industry map is empty, citic_daily levels may be null")

    target_codes_by_source: dict[str, set[str]] = {}
    if not args.skip_factors:
        if do_market:
            target_codes_by_source["market"] = set(index_codes)
        if do_citic:
            # idx_factor_pro(trade_date=...) already returns all citic indices for the day.
            target_codes_by_source["ci"] = set()
        if do_sw_factor:
            # idx_factor_pro(trade_date=...) already returns all shenwan indices for the day.
            target_codes_by_source["sw"] = set()
        if target_codes_by_source:
            logger.info(
                "index_factor targets: %s",
                ", ".join(
                    f"{key}={'all' if len(value) == 0 else len(value)}"
                    for key, value in sorted(target_codes_by_source.items())
                ),
            )
        else:
            logger.info("skip index_factor_pro: no target sources")

    total_citic = 0
    total_market = 0
    total_factor = 0
    skipped_non_trading = 0
    total_factor_counts = {"market": 0, "sw": 0, "ci": 0}
    synced_dates: list[str] = []

    progress = tqdm(date_list, total=len(date_list), desc="sync_zhishu_data", unit="day", dynamic_ncols=True)
    for idx, trade_date in enumerate(progress, start=1):
        if not is_sync_date(trade_date):
            skipped_non_trading += 1
            progress.set_postfix(date=trade_date, status="skip")
            continue

        synced_dates.append(trade_date)
        day_start = time.time()
        citic_count: int | str = "-"
        market_count: int | str = "-"
        factor_count: int | str = "-"
        factor_counts_day = {"market": 0, "sw": 0, "ci": 0}
        errors: list[str] = []
        timings: dict[str, float] = {}

        if do_citic:
            try:
                t0 = time.time()
                citic_value = sync_citic_daily_for_date(
                    trade_date, level_map=level_map, name_map=name_map, verbose=False
                )
                timings["citic"] = time.time() - t0
                citic_count = citic_value
                total_citic += citic_value
            except Exception as exc:
                errors.append(f"citic={exc}")

        if do_market:
            try:
                t0 = time.time()
                market_value = sync_market_dailybasic_for_date(
                    trade_date=trade_date,
                    index_codes=index_codes,
                )
                timings["market"] = time.time() - t0
                market_count = market_value
                total_market += market_value
            except Exception as exc:
                errors.append(f"market={exc}")

        if not args.skip_factors and target_codes_by_source:
            try:
                t0 = time.time()
                factor_value, factor_counts_day = sync_index_factors_for_trade_date(
                    trade_date=trade_date,
                    target_codes_by_source=target_codes_by_source,
                    sleep_seconds=args.sleep,
                )
                timings["factor"] = time.time() - t0
                factor_count = factor_value
                total_factor += factor_value
                for key in total_factor_counts.keys():
                    total_factor_counts[key] += factor_counts_day.get(key, 0)
            except Exception as exc:
                errors.append(f"factor={exc}")

        elapsed = time.time() - day_start
        progress.set_postfix(
            date=trade_date,
            citic=citic_count,
            market=market_count,
            factor=factor_count,
            f_market=factor_counts_day.get("market", 0),
            f_sw=factor_counts_day.get("sw", 0),
            f_ci=factor_counts_day.get("ci", 0),
            elapsed=f"{elapsed:.2f}s",
            errors=len(errors),
        )
        if errors:
            logger.warning("[%s/%s] %s errors: %s", idx, len(date_list), trade_date, "; ".join(errors))

    total_elapsed = time.time() - script_start
    for d in synced_dates:
        mark_sync_done(d, "sync_zhishu_data")
    logger.info(
        "sync totals: citic_daily=%s market_dailybasic=%s idx_factor=%s (market=%s sw=%s ci=%s) skipped_non_trading=%s",
        total_citic,
        total_market,
        total_factor,
        total_factor_counts["market"],
        total_factor_counts["sw"],
        total_factor_counts["ci"],
        skipped_non_trading,
    )

    logger.info("sync_zhishu_data done, elapsed=%.2fs (%.1fmin)", total_elapsed, total_elapsed / 60)


if __name__ == "__main__":
    main()
