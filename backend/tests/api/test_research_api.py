from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, require_admin_user
from app.api.routers import router as api_router


def _create_client() -> TestClient:
    app = FastAPI()
    app.include_router(api_router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: {"username": "james", "roles": ["admin"], "status": "active"}
    app.dependency_overrides[require_admin_user] = lambda: {"username": "james", "roles": ["admin"], "status": "active"}
    return TestClient(app)


def test_research_stock_overview_route_exists(monkeypatch) -> None:
    client = _create_client()
    monkeypatch.setattr(
        "app.api.routes.research.get_stock_research_overview",
        lambda ts_code: {"ts_code": ts_code, "basic": {"ts_code": ts_code}},
    )

    response = client.get("/api/research/stocks/000001.SZ/overview")

    assert response.status_code == 200
    assert response.json()["ts_code"] == "000001.SZ"


def test_research_stock_financials_route_exists(monkeypatch) -> None:
    client = _create_client()
    monkeypatch.setattr(
        "app.api.routes.research.get_stock_research_financials",
        lambda ts_code, limit=8: {  # noqa: ARG005
            "ts_code": ts_code,
            "latest_period": "20251231",
            "periods": ["20251231"],
            "indicators": [],
            "income": [],
            "balance": [],
            "cashflow": [],
        },
    )

    response = client.get("/api/research/stocks/000001.SZ/financials")

    assert response.status_code == 200
    assert response.json()["latest_period"] == "20251231"


def test_research_market_indexes_route_exists(monkeypatch) -> None:
    client = _create_client()
    monkeypatch.setattr(
        "app.api.routes.research.get_market_research_indexes",
        lambda: {
            "tracked_indexes": [{"ts_code": "000001.SH", "name": "上证指数"}],
            "latest_snapshot": [{"ts_code": "000001.SH"}],
            "available_dates": ["20260313"],
        },
    )

    response = client.get("/api/research/market/indexes")

    assert response.status_code == 200
    assert response.json()["tracked_indexes"][0]["ts_code"] == "000001.SH"
