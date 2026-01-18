from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field

from app.data.mongo import get_collection


class DailySignal(BaseModel):
    trading_date: str
    stock_code: str
    strategy: str
    signal: str
    created_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.UTC))

    @staticmethod
    def find_by_date_strategy(start_date: str, end_date: str, strategy: str) -> list["DailySignal"]:
        if not start_date or not end_date:
            raise ValueError("start_date and end_date are required")
        if not strategy:
            raise ValueError("strategy is required")

        collection = get_collection("daily_signal")
        query = {
            "trading_date": {"$gte": start_date, "$lte": end_date},
            "strategy": strategy,
        }
        results: list[DailySignal] = []
        for doc in collection.find(query):
            doc.pop("_id", None)
            results.append(DailySignal(**doc))
        return results
