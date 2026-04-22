from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.api.routers import router as api_router


def _create_client() -> TestClient:
    app = FastAPI()
    app.include_router(api_router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: {
        "username": "james",
        "roles": ["admin"],
        "status": "active",
    }
    return TestClient(app)


def test_get_daily_stock_signal_dates(monkeypatch) -> None:
    client = _create_client()
    monkeypatch.setattr(
        "app.api.routes.daily_stock_signals.list_available_daily_stock_signal_dates",
        lambda limit=365: ["20260417", "20260416"],
    )

    response = client.get("/api/daily-stock-signals/dates")

    assert response.status_code == 200
    assert response.json() == {"items": ["20260417", "20260416"], "total": 2}


def test_get_daily_stock_signal_overview(monkeypatch) -> None:
    client = _create_client()
    monkeypatch.setattr(
        "app.api.routes.daily_stock_signals.get_daily_stock_signals_overview",
        lambda trade_date=None, top_n=50: {
            "trade_date": trade_date or "20260417",
            "buy_signals": [],
            "sell_signals": [],
            "buy_resonance": [],
            "sell_resonance": [],
            "top_n": top_n,
        },
    )

    response = client.get("/api/daily-stock-signals/overview", params={"trade_date": "20260417"})

    assert response.status_code == 200
    assert response.json()["trade_date"] == "20260417"
    assert response.json()["top_n"] == 50


def test_get_daily_stock_signal_by_type_returns_404_when_missing(monkeypatch) -> None:
    client = _create_client()
    monkeypatch.setattr(
        "app.api.routes.daily_stock_signals.get_daily_stock_signal_by_type",
        lambda trade_date, signal_type: None,
    )

    response = client.get(
        "/api/daily-stock-signals/by-type",
        params={"trade_date": "20260417", "signal_type": "buy_macd_kdj_double_cross"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "signal group not found"
