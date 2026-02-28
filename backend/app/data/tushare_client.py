from __future__ import annotations

import time
from collections.abc import Callable

import pandas as pd
import requests

from app.core.config import settings

_RETRY_TIMES = 4
_RETRY_SLEEP_SECONDS = 1.2
_TUSHARE_API_URL = "http://api.waditu.com/dataapi"


def _ensure_token() -> None:
    if not settings.tushare_token:
        raise ValueError("TUSHARE_TOKEN is required")


def _query_pro(
    api_name: str,
    *,
    fields: str = "",
    params: dict[str, object] | None = None,
    timeout: int = 30,
) -> pd.DataFrame:
    _ensure_token()

    req_params = {
        "api_name": api_name,
        "token": settings.tushare_token,
        "params": params or {},
        "fields": fields,
    }
    headers = {
        # Workaround for occasional brotli decode failures in urllib3 + brotlicffi.
        "Accept-Encoding": "gzip, deflate",
        "Content-Type": "application/json",
    }
    response = requests.post(
        f"{_TUSHARE_API_URL}/{api_name}",
        json=req_params,
        headers=headers,
        timeout=timeout,
    )
    if not response:
        return pd.DataFrame()

    result = response.json()
    if result.get("code") != 0:
        raise ValueError(str(result.get("msg") or "TuShare query failed"))

    data = result.get("data") or {}
    columns = data.get("fields") or []
    items = data.get("items") or []
    return pd.DataFrame(items, columns=columns)


def _request_with_retry(request_fn: Callable[[], pd.DataFrame]) -> pd.DataFrame:
    last_exc: Exception | None = None
    for attempt in range(1, _RETRY_TIMES + 1):
        try:
            return request_fn()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt >= _RETRY_TIMES:
                break
            time.sleep(_RETRY_SLEEP_SECONDS * attempt)
    raise ValueError(f"TuShare request failed: {last_exc}") from last_exc


def fetch_stock_basic() -> pd.DataFrame:
    df = _request_with_retry(
        lambda: _query_pro(
            "stock_basic",
            fields="ts_code,symbol,name,area,industry,market,list_date",
            params={"exchange": "", "list_status": "L"},
        )
    )
    if df is None or df.empty:
        raise ValueError("TuShare returned empty stock_basic data")
    return df


def fetch_shenwan_classify(src: str, level: str) -> pd.DataFrame:
    df = _request_with_retry(
        lambda: _query_pro("index_classify", params={"src": src, "level": level})
    )
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
    df = _request_with_retry(
        lambda: _query_pro(
            "index_member_all",
            params={
                "l1_code": l1_code or "",
                "l2_code": l2_code or "",
                "l3_code": l3_code or "",
                "ts_code": ts_code or "",
                "is_new": is_new or "",
            },
        )
    )
    if df is None:
        raise ValueError("TuShare returned empty shenwan member data")
    return df


def fetch_shenwan_daily(trade_date: str) -> pd.DataFrame:
    if not trade_date:
        raise ValueError("trade_date is required")

    df = _request_with_retry(
        lambda: _query_pro("sw_daily", params={"trade_date": trade_date})
    )
    if df is None:
        return pd.DataFrame()
    return df


def fetch_trade_calendar(
    *,
    exchange: str = "SSE",
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    if not start_date or not end_date:
        raise ValueError("start_date and end_date are required")

    df = _request_with_retry(
        lambda: _query_pro(
            "trade_cal",
            fields="exchange,cal_date,is_open,pretrade_date",
            params={"exchange": exchange, "start_date": start_date, "end_date": end_date},
        )
    )
    if df is None:
        return pd.DataFrame()
    return df


def fetch_citic_members(
    *,
    l1_code: str | None = None,
    l2_code: str | None = None,
    l3_code: str | None = None,
    ts_code: str | None = None,
    is_new: str | None = None,
) -> pd.DataFrame:
    df = _request_with_retry(
        lambda: _query_pro(
            "ci_index_member",
            params={
                "l1_code": l1_code or "",
                "l2_code": l2_code or "",
                "l3_code": l3_code or "",
                "ts_code": ts_code or "",
                "is_new": is_new or "",
            },
        )
    )
    if df is None:
        return pd.DataFrame()
    return df


def fetch_citic_daily(
    *,
    ts_code: str | None = None,
    trade_date: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pd.DataFrame:
    df = _request_with_retry(
        lambda: _query_pro(
            "ci_daily",
            params={
                "ts_code": ts_code or "",
                "trade_date": trade_date or "",
                "start_date": start_date or "",
                "end_date": end_date or "",
            },
        )
    )
    if df is None:
        return pd.DataFrame()
    return df


def fetch_index_dailybasic(
    *,
    ts_code: str | None = None,
    trade_date: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pd.DataFrame:
    df = _request_with_retry(
        lambda: _query_pro(
            "index_dailybasic",
            params={
                "ts_code": ts_code or "",
                "trade_date": trade_date or "",
                "start_date": start_date or "",
                "end_date": end_date or "",
            },
        )
    )
    if df is None:
        return pd.DataFrame()
    return df


def fetch_index_weight(
    *,
    index_code: str,
    trade_date: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pd.DataFrame:
    if not index_code:
        raise ValueError("index_code is required")
    df = _request_with_retry(
        lambda: _query_pro(
            "index_weight",
            params={
                "index_code": index_code,
                "trade_date": trade_date or "",
                "start_date": start_date or "",
                "end_date": end_date or "",
            },
        )
    )
    if df is None:
        return pd.DataFrame()
    return df


def fetch_idx_factor_pro(
    *,
    ts_code: str | None = None,
    trade_date: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> pd.DataFrame:
    df = _request_with_retry(
        lambda: _query_pro(
            "idx_factor_pro",
            params={
                "ts_code": ts_code or "",
                "trade_date": trade_date or "",
                "start_date": start_date or "",
                "end_date": end_date or "",
                "limit": limit if limit is not None else "",
                "offset": offset if offset is not None else "",
            },
        )
    )
    if df is None:
        return pd.DataFrame()
    return df


def fetch_stk_factor_pro(
    *,
    trade_date: str,
    fields: str = "",
) -> pd.DataFrame:
    if not trade_date:
        raise ValueError("trade_date is required")

    df = _request_with_retry(
        lambda: _query_pro(
            "stk_factor_pro",
            fields=fields or "",
            params={"trade_date": trade_date},
        )
    )
    if df is None:
        return pd.DataFrame()
    return df
