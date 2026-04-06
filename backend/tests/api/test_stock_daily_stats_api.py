from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.api.routers import router as api_router
from app.schemas.stock_daily_stats import StockDailyStatsScreenResult


def create_test_client() -> TestClient:
    app = FastAPI()
    app.include_router(api_router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: {"username": "james", "status": "active"}
    return TestClient(app)


class StockDailyStatsApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.client = create_test_client()

    def test_invalid_payload_returns_400(self) -> None:
        cases = [
            ({"start_date": "20260306", "end_date": "20260220"}, "start_date cannot be after end_date"),
            ({"lookback_days": 0}, "lookback_days must be greater than 0"),
            ({"lookback_days": 10, "sort_by": "unknown"}, "sort_by must be one of"),
            ({"lookback_days": 10, "page": 0}, "page must be greater than 0"),
        ]

        for payload, message in cases:
            with self.subTest(payload=payload):
                response = self.client.post("/api/stocks/daily/stats/screen", json=payload)
                self.assertEqual(400, response.status_code)
                self.assertIn(message, response.json()["detail"])

    @patch("app.api.routes.agent_required_api.screen_stock_daily_stats")
    def test_empty_result_returns_200_with_empty_list(self, mocked_service) -> None:
        mocked_service.return_value = StockDailyStatsScreenResult(data=[], total=0, page=1, page_size=100)

        response = self.client.post("/api/stocks/daily/stats/screen", json={"lookback_days": 10})

        self.assertEqual(200, response.status_code)
        self.assertEqual(
            {
                "code": 200,
                "data": [],
                "total": 0,
                "page": 1,
                "page_size": 100,
            },
            response.json(),
        )


if __name__ == "__main__":
    unittest.main()
