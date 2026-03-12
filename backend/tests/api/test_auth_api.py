from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.api.routes.auth as auth_routes
from app.api.deps import get_current_user
from app.api.routes.auth import router as auth_router


def create_auth_client() -> TestClient:
    app = FastAPI()
    app.include_router(auth_router, prefix="/api")
    return TestClient(app, raise_server_exceptions=False)


def test_login_proxies_to_personal_authenticator_without_refresh_cookie(monkeypatch) -> None:
    client = create_auth_client()

    monkeypatch.setattr(
        auth_routes,
        "_login_with_personal_authenticator",
        lambda username, password: {
            "access_token": "remote-access-token",
            "refresh_token": "remote-refresh-token",
            "token_type": "bearer",
        },
        raising=False,
    )
    response = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "secret"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "access_token": "remote-access-token",
        "refresh_token": "remote-refresh-token",
        "token_type": "bearer",
    }
    assert "set-cookie" not in {key.lower(): value for key, value in response.headers.items()}


def test_refresh_proxies_to_personal_authenticator(monkeypatch) -> None:
    client = create_auth_client()

    monkeypatch.setattr(
        auth_routes,
        "_refresh_with_personal_authenticator",
        lambda refresh_token: {
            "access_token": "rotated-access-token",
            "refresh_token": "rotated-refresh-token",
            "token_type": "bearer",
        },
        raising=False,
    )
    response = client.post("/api/auth/refresh", json={"refresh_token": "original-refresh-token"})

    assert response.status_code == 200
    assert response.json() == {
        "access_token": "rotated-access-token",
        "refresh_token": "rotated-refresh-token",
        "token_type": "bearer",
    }


def test_refresh_requires_refresh_token_field() -> None:
    client = create_auth_client()

    response = client.post("/api/auth/refresh", json={})

    assert response.status_code == 400


def test_logout_revokes_refresh_token(monkeypatch) -> None:
    client = create_auth_client()
    seen: list[str | None] = []

    monkeypatch.setattr(
        auth_routes,
        "_logout_with_personal_authenticator",
        lambda refresh_token: seen.append(refresh_token),
        raising=False,
    )

    response = client.post("/api/auth/logout", json={"refresh_token": "original-refresh-token"})

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert seen == ["original-refresh-token"]


def test_me_includes_roles_from_personal_authenticator_identity() -> None:
    app = FastAPI()
    app.include_router(auth_router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: {
        "_id": "user-1",
        "username": "alice",
        "display_name": "Alice",
        "status": "active",
        "roles": ["admin"],
        "created_at": None,
        "updated_at": None,
        "last_login_at": None,
    }
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/api/auth/me")

    assert response.status_code == 200
    assert response.json()["roles"] == ["admin"]
