from __future__ import annotations

import abc
import os
from dataclasses import dataclass
from datetime import date
from typing import Iterable, List, Sequence

from .models import BasicInfo, DailyBar


class BaseDataProvider(abc.ABC):
    """
    Abstract provider for fetching basic info and daily bars.

    Implementations can wrap third-party APIs or local data sources.
    """

    @abc.abstractmethod
    def fetch_basic_info(self, as_of: date) -> Iterable[BasicInfo]:
        """
        Return iterable of BasicInfo as of the given date.
        """

        raise NotImplementedError

    @abc.abstractmethod
    def fetch_daily_bars(self, trade_date: date) -> Iterable[DailyBar]:
        """
        Return iterable of DailyBar for the given trade_date.
        """

        raise NotImplementedError


class InMemoryProvider(BaseDataProvider):
    """
    Simple provider backed by in-memory lists, useful for tests and demos.
    """

    def __init__(self, basic_infos: Iterable[BasicInfo], daily_bars: Iterable[DailyBar]):
        self.basic_infos = list(basic_infos)
        self.daily_bars = list(daily_bars)

    def fetch_basic_info(self, as_of: date) -> Iterable[BasicInfo]:
        # In-memory demo provider ignores as_of filtering and returns all.
        return self.basic_infos

    def fetch_daily_bars(self, trade_date: date) -> Iterable[DailyBar]:
        return [bar for bar in self.daily_bars if bar.trade_date == trade_date]


# ---- TuShare Provider ---------------------------------------------------- #


class TushareAPIError(RuntimeError):
    pass


@dataclass
class TushareClient:
    """
    Minimal TuShare Pro client for `stock_basic` and `daily`.
    """

    token: str
    url: str = "https://api.tushare.pro"

    def _post(self, api_name: str, params: dict, fields: Sequence[str]) -> List[dict]:
        import requests

        payload = {"api_name": api_name, "token": self.token, "params": params, "fields": ",".join(fields)}
        resp = requests.post(self.url, json=payload, timeout=30)
        data = resp.json()
        if data.get("code") != 0:
            raise TushareAPIError(f"TuShare API error: {data}")
        fields_returned = data["data"]["fields"]
        items = []
        for row in data["data"]["items"]:
            items.append({k: v for k, v in zip(fields_returned, row)})
        return items

    def fetch_stock_basic(self, list_status: str = "L") -> List[dict]:
        fields = ["ts_code", "name", "market", "list_date", "exchange", "list_status", "industry"]
        return self._post("stock_basic", {"list_status": list_status, "fields": ",".join(fields)}, fields)

    def fetch_daily(self, trade_date: date) -> List[dict]:
        fields = [
            "ts_code",
            "trade_date",
            "open",
            "high",
            "low",
            "close",
            "pre_close",
            "pct_chg",
            "vol",
            "amount",
        ]
        return self._post("daily", {"trade_date": trade_date.strftime("%Y%m%d")}, fields)


class TushareProvider(BaseDataProvider):
    """
    TuShare-backed provider. Token should be supplied via constructor or
    environment variable TUSHARE_TOKEN.
    """

    def __init__(self, token: str | None = None, client: TushareClient | None = None):
        token = token or os.environ.get("TUSHARE_TOKEN")
        if not token:
            raise ValueError("TuShare token is required. Provide via constructor or TUSHARE_TOKEN env var.")
        self.client = client or TushareClient(token=token)

    def fetch_basic_info(self, as_of: date) -> Iterable[BasicInfo]:
        from .models import coerce_basic_info

        records = self.client.fetch_stock_basic(list_status="L")
        # TuShare list_date is YYYYMMDD; convert to YYYY-MM-DD for coerce_date
        for rec in records:
            if isinstance(rec.get("list_date"), str) and len(rec["list_date"]) == 8:
                rec["list_date"] = f"{rec['list_date'][:4]}-{rec['list_date'][4:6]}-{rec['list_date'][6:]}"
            rec["market"] = rec.get("market") or (rec.get("exchange") or "").replace("SSE", "SH").replace("SZSE", "SZ")
            rec["is_active"] = rec.get("list_status", "L") == "L"
        return coerce_basic_info(records)

    def fetch_daily_bars(self, trade_date: date) -> Iterable[DailyBar]:
        from .models import coerce_daily_bars

        records = self.client.fetch_daily(trade_date)
        for rec in records:
            # TuShare trade_date is YYYYMMDD
            if isinstance(rec.get("trade_date"), str) and len(rec["trade_date"]) == 8:
                rec["trade_date"] = f"{rec['trade_date'][:4]}-{rec['trade_date'][4:6]}-{rec['trade_date'][6:]}"
        return coerce_daily_bars(records)
