from __future__ import annotations

from datetime import date
from typing import Iterable, Optional

from .models import BasicInfo, DailyBar, ensure_unique
from .provider import BaseDataProvider
from .storage import SQLiteStorage


class DailyIngestor:
    """
    Pulls daily data from a provider and persists it into storage.
    """

    def __init__(self, provider: BaseDataProvider, storage: SQLiteStorage):
        self.provider = provider
        self.storage = storage

    def ingest(self, trade_date: date, refresh_basic_info: bool = True) -> dict:
        """
        Ingest daily bars for the given date and optionally refresh basic info.
        """

        result = {"basic_info": 0, "daily_bars": 0}
        if refresh_basic_info:
            basic_infos = self._validate_basic_info(self.provider.fetch_basic_info(trade_date))
            result["basic_info"] = self.storage.upsert_basic_info(basic_infos)

        bars = self._validate_daily_bars(self.provider.fetch_daily_bars(trade_date))
        result["daily_bars"] = self.storage.upsert_daily_bars(bars)
        return result

    def _validate_basic_info(self, infos: Iterable[BasicInfo]) -> list[BasicInfo]:
        unique_infos = ensure_unique(list(infos))
        for info in unique_infos:
            if not info.ts_code:
                raise ValueError("ts_code cannot be empty")
            if not info.name:
                raise ValueError(f"name missing for {info.ts_code}")
            if not info.market:
                raise ValueError(f"market missing for {info.ts_code}")
        return unique_infos

    def _validate_daily_bars(self, bars: Iterable[DailyBar]) -> list[DailyBar]:
        unique_bars = ensure_unique(list(bars))
        for bar in unique_bars:
            if bar.high < bar.low:
                raise ValueError(f"high < low for {bar.ts_code} on {bar.trade_date}")
        return unique_bars
