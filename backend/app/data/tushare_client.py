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
