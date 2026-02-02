from __future__ import annotations

import pandas as pd
import tushare as ts

from app.core.config import settings


def fetch_stock_basic() -> pd.DataFrame:
    if not settings.tushare_token:
        raise ValueError("TUSHARE_TOKEN is required")

    try:
        pro = ts.pro_api(settings.tushare_token)
        df = pro.stock_basic(
            exchange="",
            list_status="L",
            fields="ts_code,symbol,name,area,industry,market,list_date",
        )
    except Exception as exc:
        raise ValueError(f"TuShare request failed: {exc}") from exc

    if df is None or df.empty:
        raise ValueError("TuShare returned empty stock_basic data")
    return df


def fetch_shenwan_classify(src: str, level: str) -> pd.DataFrame:
    if not settings.tushare_token:
        raise ValueError("TUSHARE_TOKEN is required")

    try:
        pro = ts.pro_api(settings.tushare_token)
        df = pro.index_classify(src=src, level=level)
    except Exception as exc:
        raise ValueError(f"TuShare request failed: {exc}") from exc

    if df is None:
        raise ValueError("TuShare returned empty shenwan classify data")
    return df


def fetch_shenwan_members(
    *,
    l1_code: str | None = None,
    l2_code: str | None = None,
    l3_code: str | None = None,
    ts_code: str | None = None,
    is_new: str | None = None,
) -> pd.DataFrame:
    if not settings.tushare_token:
        raise ValueError("TUSHARE_TOKEN is required")

    try:
        pro = ts.pro_api(settings.tushare_token)
        df = pro.index_member_all(
            l1_code=l1_code or "",
            l2_code=l2_code or "",
            l3_code=l3_code or "",
            ts_code=ts_code or "",
            is_new=is_new or "",
        )
    except Exception as exc:
        raise ValueError(f"TuShare request failed: {exc}") from exc

    if df is None:
        raise ValueError("TuShare returned empty shenwan member data")
    return df


def fetch_shenwan_daily(trade_date: str) -> pd.DataFrame:
    if not settings.tushare_token:
        raise ValueError("TUSHARE_TOKEN is required")

    if not trade_date:
        raise ValueError("trade_date is required")

    try:
        pro = ts.pro_api(settings.tushare_token)
        df = pro.sw_daily(trade_date=trade_date)
    except Exception as exc:
        raise ValueError(f"TuShare request failed: {exc}") from exc

    if df is None:
        return pd.DataFrame()
    return df


def fetch_trade_calendar(
    *,
    exchange: str = "SSE",
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    if not settings.tushare_token:
        raise ValueError("TUSHARE_TOKEN is required")

    if not start_date or not end_date:
        raise ValueError("start_date and end_date are required")

    try:
        pro = ts.pro_api(settings.tushare_token)
        df = pro.trade_cal(
            exchange=exchange,
            start_date=start_date,
            end_date=end_date,
            fields="exchange,cal_date,is_open,pretrade_date",
        )
    except Exception as exc:
        raise ValueError(f"TuShare request failed: {exc}") from exc

    if df is None:
        return pd.DataFrame()
    return df
