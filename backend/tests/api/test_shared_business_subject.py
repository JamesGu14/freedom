from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.api.routes.strategies import router as strategies_router
import app.api.routes.strategies as strategies_routes


def test_strategy_creation_reuses_shared_business_subject(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(strategies_router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: {
        "_id": "user-1",
        "username": "alice",
        "display_name": "Alice",
        "status": "active",
        "roles": ["user"],
    }
    client = TestClient(app, raise_server_exceptions=False)
    captured: dict[str, object] = {}

    def fake_create_strategy(**kwargs):
        captured.update(kwargs)
        return {"id": "strategy-1", **kwargs}

    monkeypatch.setattr(strategies_routes, "create_strategy", fake_create_strategy)

    response = client.post(
        "/api/strategies",
        json={
            "name": "Test Strategy",
            "strategy_key": "test_strategy",
            "description": "",
            "owner": "",
        },
    )

    assert response.status_code == 200
    assert captured["created_by"] == "james"
