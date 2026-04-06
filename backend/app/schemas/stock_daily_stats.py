from __future__ import annotations

from pydantic import BaseModel, Field


class StockDailyStatsScreenRequest(BaseModel):
    start_date: str | None = None
    end_date: str | None = None
    lookback_days: int | None = None
    universe: str = "all_a"
    ts_codes: list[str] = Field(default_factory=list)
    industry_source: str | None = None
    industry_codes: list[str] = Field(default_factory=list)
    up_days_gte: int | None = None
    pct_change_gte: float | None = None
    max_up_streak_gte: int | None = None
    avg_amount_gte: float | None = None
    exclude_st: bool = False
    exclude_suspended: bool = False
    sort_by: str = "up_days"
    sort_order: str = "desc"
    page: int = 1
    page_size: int = 100


class StockDailyStatsScreenItem(BaseModel):
    ts_code: str
    name: str | None = None
    start_date: str
    end_date: str
    trade_days: int
    up_days: int
    down_days: int
    flat_days: int
    pct_change: float
    max_up_streak: int
    max_down_streak: int
    avg_amount: float
    latest_close: float
    latest_pct_chg: float


class StockDailyStatsScreenResult(BaseModel):
    data: list[StockDailyStatsScreenItem] = Field(default_factory=list)
    total: int
    page: int
    page_size: int
