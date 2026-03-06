from __future__ import annotations

import unittest

import pandas as pd

from app.schemas.stock_daily_stats import StockDailyStatsScreenRequest
from app.services.stock_daily_stats_service import (
    NormalizedScreenRequest,
    build_stock_daily_stats_items,
    filter_sort_paginate_stock_daily_stats,
    normalize_screen_request,
    resolve_screen_trade_dates,
)


class NormalizeScreenRequestTestCase(unittest.TestCase):
    def test_normalize_request_validates_required_modes(self) -> None:
        with self.assertRaisesRegex(ValueError, "either start_date or lookback_days is required"):
            normalize_screen_request(StockDailyStatsScreenRequest())


class ResolveScreenTradeDatesTestCase(unittest.TestCase):
    def test_explicit_range_takes_priority_over_lookback(self) -> None:
        request = NormalizedScreenRequest(
            start_date="20260220",
            end_date="20260306",
            lookback_days=10,
            universe="all_a",
            ts_codes=[],
            industry_source=None,
            industry_codes=[],
            up_days_gte=None,
            pct_change_gte=None,
            max_up_streak_gte=None,
            avg_amount_gte=None,
            exclude_st=False,
            exclude_suspended=False,
            sort_by="up_days",
            sort_order="desc",
            page=1,
            page_size=100,
        )

        calls: list[str] = []

        def latest_trade_date_getter(*, exchange: str, before_or_on: str | None = None) -> str | None:
            calls.append(f"latest:{before_or_on}")
            return "20260306"

        def open_trade_dates_getter(*, start_date: str, end_date: str, exchange: str) -> list[str]:
            calls.append(f"open:{start_date}:{end_date}")
            return ["20260224", "20260225", "20260226"]

        def recent_trade_dates_getter(*, end_date: str, limit: int, exchange: str) -> list[str]:
            calls.append(f"recent:{end_date}:{limit}")
            return ["20260220", "20260221"]

        resolved = resolve_screen_trade_dates(
            request,
            latest_trade_date_getter=latest_trade_date_getter,
            open_trade_dates_getter=open_trade_dates_getter,
            recent_trade_dates_getter=recent_trade_dates_getter,
        )

        self.assertEqual("20260224", resolved.start_date)
        self.assertEqual("20260226", resolved.end_date)
        self.assertEqual(["20260224", "20260225", "20260226"], resolved.trade_dates)
        self.assertEqual(["latest:20260306", "open:20260220:20260306"], calls)


class BuildStockDailyStatsItemsTestCase(unittest.TestCase):
    def test_build_items_calculates_expected_metrics(self) -> None:
        frame = pd.DataFrame(
            [
                {"ts_code": "000001.SZ", "trade_date": "20260304", "close": 11.0, "pre_close": 10.0, "pct_chg": 10.0, "amount": 100.0},
                {"ts_code": "000001.SZ", "trade_date": "20260305", "close": 12.0, "pre_close": 11.0, "pct_chg": 9.0909, "amount": 200.0},
                {"ts_code": "000001.SZ", "trade_date": "20260306", "close": 11.0, "pre_close": 12.0, "pct_chg": None, "amount": 300.0},
                {"ts_code": "000002.SZ", "trade_date": "20260304", "close": 8.0, "pre_close": None, "pct_chg": 1.0, "amount": 50.0},
            ]
        )

        items = build_stock_daily_stats_items(
            frame,
            trade_dates=["20260304", "20260305", "20260306"],
            basics_by_code={"000001.SZ": {"name": "平安银行"}},
            start_date="20260304",
            end_date="20260306",
        )

        self.assertEqual(1, len(items))
        item = items[0]
        self.assertEqual("000001.SZ", item["ts_code"])
        self.assertEqual("平安银行", item["name"])
        self.assertEqual(3, item["trade_days"])
        self.assertEqual(2, item["up_days"])
        self.assertEqual(1, item["down_days"])
        self.assertEqual(0, item["flat_days"])
        self.assertAlmostEqual(10.0, item["pct_change"], places=6)
        self.assertEqual(2, item["max_up_streak"])
        self.assertEqual(1, item["max_down_streak"])
        self.assertAlmostEqual(200.0, item["avg_amount"], places=6)
        self.assertAlmostEqual(11.0, item["latest_close"], places=6)
        self.assertAlmostEqual(-8.3333333333, item["latest_pct_chg"], places=6)


class FilterSortPaginateStockDailyStatsTestCase(unittest.TestCase):
    def test_filters_sort_and_paginate(self) -> None:
        request = NormalizedScreenRequest(
            start_date=None,
            end_date=None,
            lookback_days=10,
            universe="all_a",
            ts_codes=[],
            industry_source=None,
            industry_codes=[],
            up_days_gte=8,
            pct_change_gte=5.0,
            max_up_streak_gte=3,
            avg_amount_gte=100.0,
            exclude_st=False,
            exclude_suspended=True,
            sort_by="pct_change",
            sort_order="desc",
            page=1,
            page_size=1,
        )
        items = [
            {
                "ts_code": "000002.SZ",
                "name": "B",
                "start_date": "20260220",
                "end_date": "20260306",
                "trade_days": 10,
                "up_days": 9,
                "down_days": 1,
                "flat_days": 0,
                "pct_change": 9.5,
                "max_up_streak": 4,
                "max_down_streak": 1,
                "avg_amount": 300.0,
                "latest_close": 11.0,
                "latest_pct_chg": 1.1,
            },
            {
                "ts_code": "000001.SZ",
                "name": "A",
                "start_date": "20260220",
                "end_date": "20260306",
                "trade_days": 10,
                "up_days": 8,
                "down_days": 2,
                "flat_days": 0,
                "pct_change": 8.0,
                "max_up_streak": 3,
                "max_down_streak": 1,
                "avg_amount": 200.0,
                "latest_close": 10.0,
                "latest_pct_chg": 1.0,
            },
            {
                "ts_code": "000003.SZ",
                "name": "C",
                "start_date": "20260220",
                "end_date": "20260306",
                "trade_days": 9,
                "up_days": 8,
                "down_days": 1,
                "flat_days": 0,
                "pct_change": 7.0,
                "max_up_streak": 3,
                "max_down_streak": 1,
                "avg_amount": 200.0,
                "latest_close": 9.0,
                "latest_pct_chg": 0.5,
            },
        ]

        result = filter_sort_paginate_stock_daily_stats(items, request, expected_trade_days=10)

        self.assertEqual(2, result.total)
        self.assertEqual(1, len(result.data))
        self.assertEqual("000002.SZ", result.data[0].ts_code)


if __name__ == "__main__":
    unittest.main()
