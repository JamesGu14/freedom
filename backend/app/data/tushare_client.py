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


def fetch_index_basic(
    *,
    market: str = "",
    publisher: str = "",
    category: str = "",
) -> pd.DataFrame:
    params = {
        k: v
        for k, v in {
            "market": market,
            "publisher": publisher,
            "category": category,
        }.items()
        if v != ""
    }
    df = _request_with_retry(lambda: _query_pro("index_basic", params=params))
    if df is None:
        return pd.DataFrame()
    return df


def fetch_index_daily(
    *,
    ts_code: str,
    trade_date: str = "",
    start_date: str = "",
    end_date: str = "",
    limit: int | None = None,
    offset: int | None = None,
) -> pd.DataFrame:
    if not ts_code:
        raise ValueError("ts_code is required")
    params = {
        k: v
        for k, v in {
            "ts_code": ts_code,
            "trade_date": trade_date,
            "start_date": start_date,
            "end_date": end_date,
            "limit": limit if limit is not None else "",
            "offset": offset if offset is not None else "",
        }.items()
        if v != ""
    }
    df = _request_with_retry(lambda: _query_pro("index_daily", params=params))
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


def fetch_cyq_perf(
    *,
    ts_code: str = "",
    trade_date: str = "",
    start_date: str = "",
    end_date: str = "",
) -> pd.DataFrame:
    params = {k: v for k, v in {"ts_code": ts_code, "trade_date": trade_date, "start_date": start_date, "end_date": end_date}.items() if v}
    df = _request_with_retry(lambda: _query_pro("cyq_perf", params=params))
    if df is None:
        return pd.DataFrame()
    return df


def fetch_cyq_chips(
    ts_code: str,
    *,
    start_date: str = "",
    end_date: str = "",
) -> pd.DataFrame:
    params: dict[str, object] = {"ts_code": ts_code}
    if start_date:
        params["start_date"] = start_date
    if end_date:
        params["end_date"] = end_date
    df = _request_with_retry(lambda: _query_pro("cyq_chips", params=params))
    if df is None:
        return pd.DataFrame()
    return df


def fetch_ccass_hold(
    *,
    ts_code: str = "",
    trade_date: str = "",
    start_date: str = "",
    end_date: str = "",
) -> pd.DataFrame:
    params = {k: v for k, v in {"ts_code": ts_code, "trade_date": trade_date, "start_date": start_date, "end_date": end_date}.items() if v}
    df = _request_with_retry(lambda: _query_pro("ccass_hold", params=params))
    if df is None:
        return pd.DataFrame()
    return df


def fetch_hk_hold(
    *,
    ts_code: str = "",
    trade_date: str = "",
    start_date: str = "",
    end_date: str = "",
    exchange: str = "",
) -> pd.DataFrame:
    params = {k: v for k, v in {"ts_code": ts_code, "trade_date": trade_date, "start_date": start_date, "end_date": end_date, "exchange": exchange}.items() if v}
    df = _request_with_retry(lambda: _query_pro("hk_hold", params=params))
    if df is None:
        return pd.DataFrame()
    return df


def fetch_stk_surv(
    *,
    ts_code: str = "",
    trade_date: str = "",
    start_date: str = "",
    end_date: str = "",
) -> pd.DataFrame:
    params = {k: v for k, v in {"ts_code": ts_code, "trade_date": trade_date, "start_date": start_date, "end_date": end_date}.items() if v}
    df = _request_with_retry(lambda: _query_pro("stk_surv", params=params))
    if df is None:
        return pd.DataFrame()
    return df


def fetch_margin(
    *,
    trade_date: str = "",
    start_date: str = "",
    end_date: str = "",
    exchange_id: str = "",
    limit: int | None = None,
    offset: int | None = None,
) -> pd.DataFrame:
    params = {
        k: v
        for k, v in {
            "trade_date": trade_date,
            "start_date": start_date,
            "end_date": end_date,
            "exchange_id": exchange_id,
            "limit": limit if limit is not None else "",
            "offset": offset if offset is not None else "",
        }.items()
        if v != ""
    }
    df = _request_with_retry(lambda: _query_pro("margin", params=params))
    if df is None:
        return pd.DataFrame()
    return df


def fetch_margin_detail(
    *,
    trade_date: str = "",
    start_date: str = "",
    end_date: str = "",
    ts_code: str = "",
    limit: int | None = None,
    offset: int | None = None,
) -> pd.DataFrame:
    params = {
        k: v
        for k, v in {
            "trade_date": trade_date,
            "start_date": start_date,
            "end_date": end_date,
            "ts_code": ts_code,
            "limit": limit if limit is not None else "",
            "offset": offset if offset is not None else "",
        }.items()
        if v != ""
    }
    df = _request_with_retry(lambda: _query_pro("margin_detail", params=params))
    if df is None:
        return pd.DataFrame()
    return df


def fetch_moneyflow_dc(
    *,
    ts_code: str = "",
    trade_date: str = "",
    start_date: str = "",
    end_date: str = "",
) -> pd.DataFrame:
    params = {k: v for k, v in {"ts_code": ts_code, "trade_date": trade_date, "start_date": start_date, "end_date": end_date}.items() if v}
    df = _request_with_retry(lambda: _query_pro("moneyflow_dc", params=params))
    if df is None:
        return pd.DataFrame()
    return df


def fetch_moneyflow_hsgt(
    *,
    trade_date: str = "",
    start_date: str = "",
    end_date: str = "",
) -> pd.DataFrame:
    params = {k: v for k, v in {"trade_date": trade_date, "start_date": start_date, "end_date": end_date}.items() if v}
    df = _request_with_retry(lambda: _query_pro("moneyflow_hsgt", params=params))
    if df is None:
        return pd.DataFrame()
    return df


def fetch_adj_factor(
    *,
    trade_date: str = "",
    ts_code: str = "",
    start_date: str = "",
    end_date: str = "",
) -> pd.DataFrame:
    params = {k: v for k, v in {"trade_date": trade_date, "ts_code": ts_code, "start_date": start_date, "end_date": end_date}.items() if v}
    df = _request_with_retry(lambda: _query_pro("adj_factor", params=params))
    if df is None:
        return pd.DataFrame()
    return df


def fetch_suspend_d(
    *,
    ts_code: str = "",
    trade_date: str = "",
    start_date: str = "",
    end_date: str = "",
    suspend_type: str = "",
    limit: int | None = None,
    offset: int | None = None,
) -> pd.DataFrame:
    params = {
        k: v
        for k, v in {
            "ts_code": ts_code,
            "trade_date": trade_date,
            "start_date": start_date,
            "end_date": end_date,
            "suspend_type": suspend_type,
            "limit": limit if limit is not None else "",
            "offset": offset if offset is not None else "",
        }.items()
        if v != ""
    }
    df = _request_with_retry(lambda: _query_pro("suspend_d", params=params))
    if df is None:
        return pd.DataFrame()
    return df


def fetch_income(
    *,
    ts_code: str = "",
    ann_date: str = "",
    start_date: str = "",
    end_date: str = "",
    period: str = "",
    report_type: str = "",
    comp_type: str = "",
    limit: int | None = None,
    offset: int | None = None,
) -> pd.DataFrame:
    api_name = "income_vip" if not ts_code else "income"
    params = {
        k: v
        for k, v in {
            "ts_code": ts_code,
            "ann_date": ann_date,
            "start_date": start_date,
            "end_date": end_date,
            "period": period,
            "report_type": report_type,
            "comp_type": comp_type,
            "limit": limit if limit is not None else "",
            "offset": offset if offset is not None else "",
        }.items()
        if v != ""
    }
    df = _request_with_retry(lambda: _query_pro(api_name, params=params))
    if df is None:
        return pd.DataFrame()
    return df


def fetch_balancesheet(
    *,
    ts_code: str = "",
    ann_date: str = "",
    f_ann_date: str = "",
    start_date: str = "",
    end_date: str = "",
    period: str = "",
    report_type: str = "",
    comp_type: str = "",
    limit: int | None = None,
    offset: int | None = None,
) -> pd.DataFrame:
    api_name = "balancesheet_vip" if not ts_code else "balancesheet"
    params = {
        k: v
        for k, v in {
            "ts_code": ts_code,
            "ann_date": ann_date,
            "f_ann_date": f_ann_date,
            "start_date": start_date,
            "end_date": end_date,
            "period": period,
            "report_type": report_type,
            "comp_type": comp_type,
            "limit": limit if limit is not None else "",
            "offset": offset if offset is not None else "",
        }.items()
        if v != ""
    }
    df = _request_with_retry(lambda: _query_pro(api_name, params=params))
    if df is None:
        return pd.DataFrame()
    return df


def fetch_cashflow(
    *,
    ts_code: str = "",
    ann_date: str = "",
    f_ann_date: str = "",
    start_date: str = "",
    end_date: str = "",
    period: str = "",
    report_type: str = "",
    comp_type: str = "",
    limit: int | None = None,
    offset: int | None = None,
) -> pd.DataFrame:
    api_name = "cashflow_vip" if not ts_code else "cashflow"
    params = {
        k: v
        for k, v in {
            "ts_code": ts_code,
            "ann_date": ann_date,
            "f_ann_date": f_ann_date,
            "start_date": start_date,
            "end_date": end_date,
            "period": period,
            "report_type": report_type,
            "comp_type": comp_type,
            "limit": limit if limit is not None else "",
            "offset": offset if offset is not None else "",
        }.items()
        if v != ""
    }
    df = _request_with_retry(lambda: _query_pro(api_name, params=params))
    if df is None:
        return pd.DataFrame()
    return df


def fetch_fina_indicator(
    *,
    ts_code: str = "",
    ann_date: str = "",
    start_date: str = "",
    end_date: str = "",
    period: str = "",
    limit: int | None = None,
    offset: int | None = None,
) -> pd.DataFrame:
    api_name = "fina_indicator_vip" if not ts_code else "fina_indicator"
    params = {
        k: v
        for k, v in {
            "ts_code": ts_code,
            "ann_date": ann_date,
            "start_date": start_date,
            "end_date": end_date,
            "period": period,
            "limit": limit if limit is not None else "",
            "offset": offset if offset is not None else "",
        }.items()
        if v != ""
    }
    df = _request_with_retry(lambda: _query_pro(api_name, params=params))
    if df is None:
        return pd.DataFrame()
    return df


def fetch_dividend(
    *,
    ts_code: str = "",
    ann_date: str = "",
    end_date: str = "",
    limit: int | None = None,
    offset: int | None = None,
) -> pd.DataFrame:
    params = {
        k: v
        for k, v in {
            "ts_code": ts_code,
            "ann_date": ann_date,
            "end_date": end_date,
            "limit": limit if limit is not None else "",
            "offset": offset if offset is not None else "",
        }.items()
        if v != ""
    }
    df = _request_with_retry(lambda: _query_pro("dividend", params=params))
    if df is None:
        return pd.DataFrame()
    return df


def fetch_stk_holdernumber(
    *,
    ts_code: str = "",
    ann_date: str = "",
    start_date: str = "",
    end_date: str = "",
    limit: int | None = None,
    offset: int | None = None,
) -> pd.DataFrame:
    params = {
        k: v
        for k, v in {
            "ts_code": ts_code,
            "ann_date": ann_date,
            "start_date": start_date,
            "end_date": end_date,
            "limit": limit if limit is not None else "",
            "offset": offset if offset is not None else "",
        }.items()
        if v != ""
    }
    df = _request_with_retry(lambda: _query_pro("stk_holdernumber", params=params))
    if df is None:
        return pd.DataFrame()
    return df


def fetch_top10_holders(
    *,
    ts_code: str = "",
    ann_date: str = "",
    start_date: str = "",
    end_date: str = "",
    period: str = "",
    limit: int | None = None,
    offset: int | None = None,
) -> pd.DataFrame:
    params = {
        k: v
        for k, v in {
            "ts_code": ts_code,
            "ann_date": ann_date,
            "start_date": start_date,
            "end_date": end_date,
            "period": period,
            "limit": limit if limit is not None else "",
            "offset": offset if offset is not None else "",
        }.items()
        if v != ""
    }
    df = _request_with_retry(lambda: _query_pro("top10_holders", params=params))
    if df is None:
        return pd.DataFrame()
    return df


def fetch_top10_floatholders(
    *,
    ts_code: str = "",
    ann_date: str = "",
    start_date: str = "",
    end_date: str = "",
    period: str = "",
    limit: int | None = None,
    offset: int | None = None,
) -> pd.DataFrame:
    params = {
        k: v
        for k, v in {
            "ts_code": ts_code,
            "ann_date": ann_date,
            "start_date": start_date,
            "end_date": end_date,
            "period": period,
            "limit": limit if limit is not None else "",
            "offset": offset if offset is not None else "",
        }.items()
        if v != ""
    }
    df = _request_with_retry(lambda: _query_pro("top10_floatholders", params=params))
    if df is None:
        return pd.DataFrame()
    return df


def fetch_forecast(
    *,
    ts_code: str = "",
    ann_date: str = "",
    start_date: str = "",
    end_date: str = "",
    period: str = "",
    type_: str = "",
    limit: int | None = None,
    offset: int | None = None,
) -> pd.DataFrame:
    """Fetch forecast data from TuShare. ts_code is optional for querying by ann_date range."""
    params = {
        k: v
        for k, v in {
            "ts_code": ts_code,
            "ann_date": ann_date,
            "start_date": start_date,
            "end_date": end_date,
            "period": period,
            "type": type_,
            "limit": limit if limit is not None else "",
            "offset": offset if offset is not None else "",
        }.items()
        if v != ""
    }
    df = _request_with_retry(lambda: _query_pro("forecast", params=params))
    if df is None:
        return pd.DataFrame()
    return df


def fetch_express(
    *,
    ts_code: str = "",
    ann_date: str = "",
    start_date: str = "",
    end_date: str = "",
    period: str = "",
    limit: int | None = None,
    offset: int | None = None,
) -> pd.DataFrame:
    """Fetch express data from TuShare. ts_code is optional for querying by ann_date range."""
    params = {
        k: v
        for k, v in {
            "ts_code": ts_code,
            "ann_date": ann_date,
            "start_date": start_date,
            "end_date": end_date,
            "period": period,
            "limit": limit if limit is not None else "",
            "offset": offset if offset is not None else "",
        }.items()
        if v != ""
    }
    df = _request_with_retry(lambda: _query_pro("express", params=params))
    if df is None:
        return pd.DataFrame()
    return df


def fetch_fina_audit(
    *,
    ts_code: str,
    ann_date: str = "",
    start_date: str = "",
    end_date: str = "",
    period: str = "",
    limit: int | None = None,
    offset: int | None = None,
) -> pd.DataFrame:
    """Fetch fina_audit data from TuShare. ts_code is REQUIRED."""
    if not ts_code:
        raise ValueError("ts_code is required for fina_audit")
    params = {
        k: v
        for k, v in {
            "ts_code": ts_code,
            "ann_date": ann_date,
            "start_date": start_date,
            "end_date": end_date,
            "period": period,
            "limit": limit if limit is not None else "",
            "offset": offset if offset is not None else "",
        }.items()
        if v != ""
    }
    df = _request_with_retry(lambda: _query_pro("fina_audit", params=params))
    if df is None:
        return pd.DataFrame()
    return df


def fetch_fina_mainbz(
    *,
    ts_code: str,
    period: str = "",
    type_: str = "",
    start_date: str = "",
    end_date: str = "",
    limit: int | None = None,
    offset: int | None = None,
) -> pd.DataFrame:
    """Fetch fina_mainbz data from TuShare. ts_code is REQUIRED.
    
    Note: start_date/end_date here mean REPORTING PERIOD range (not announcement date).
    """
    if not ts_code:
        raise ValueError("ts_code is required for fina_mainbz")
    params = {
        k: v
        for k, v in {
            "ts_code": ts_code,
            "period": period,
            "type": type_,
            "start_date": start_date,
            "end_date": end_date,
            "limit": limit if limit is not None else "",
            "offset": offset if offset is not None else "",
        }.items()
        if v != ""
    }
    df = _request_with_retry(lambda: _query_pro("fina_mainbz", params=params))
    if df is None:
        return pd.DataFrame()
    return df


def fetch_disclosure_date(
    *,
    ts_code: str = "",
    end_date: str = "",
    pre_date: str = "",
    actual_date: str = "",
    limit: int | None = None,
    offset: int | None = None,
) -> pd.DataFrame:
    """Fetch disclosure_date data from TuShare.
    
    Note: end_date here means REPORTING PERIOD (e.g., 20241231), not announcement date range.
    Max 3000 rows per request.
    """
    params = {
        k: v
        for k, v in {
            "ts_code": ts_code,
            "end_date": end_date,
            "pre_date": pre_date,
            "actual_date": actual_date,
            "limit": limit if limit is not None else "",
            "offset": offset if offset is not None else "",
        }.items()
        if v != ""
    }
    df = _request_with_retry(lambda: _query_pro("disclosure_date", params=params))
    if df is None:
        return pd.DataFrame()
    return df
