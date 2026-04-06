from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import require_admin_user
from app.api.routes.internal_audits import router as internal_audits_router
import app.api.routes.internal_audits as internal_audits_routes


def _create_client() -> TestClient:
    app = FastAPI()
    app.include_router(internal_audits_router, prefix="/api")
    return TestClient(app, raise_server_exceptions=False)


def test_create_internal_audit_run_returns_202(monkeypatch) -> None:
    client = _create_client()
    client.app.dependency_overrides[require_admin_user] = lambda: {
        "username": "james",
        "roles": ["admin"],
    }
    monkeypatch.setattr(
        internal_audits_routes,
        "start_data_integrity_audit_run",
        lambda **kwargs: {
            "run_id": "weekly_20260321_060000",
            "status": "queued",
            "scheduled_for": kwargs["scheduled_for"],
        },
    )

    response = client.post(
        "/api/internal/audits/data-integrity/runs",
        json={"scheduled_for": "2026-03-21T06:00:00+08:00", "trigger_source": "airflow"},
    )

    assert response.status_code == 202
    assert response.json()["run_id"] == "weekly_20260321_060000"
    assert response.json()["status"] == "queued"


def test_get_internal_audit_run_returns_payload(monkeypatch) -> None:
    client = _create_client()
    client.app.dependency_overrides[require_admin_user] = lambda: {
        "username": "james",
        "roles": ["admin"],
    }
    monkeypatch.setattr(
        internal_audits_routes,
        "get_data_integrity_audit_run_status",
        lambda run_id: {"run_id": run_id, "status": "succeeded", "status_summary": {"green": 12, "yellow": 0, "red": 0}},
    )

    response = client.get("/api/internal/audits/data-integrity/runs/weekly_20260321_060000")

    assert response.status_code == 200
    assert response.json()["status"] == "succeeded"


def test_get_internal_audit_run_returns_404_when_missing(monkeypatch) -> None:
    client = _create_client()
    client.app.dependency_overrides[require_admin_user] = lambda: {
        "username": "james",
        "roles": ["admin"],
    }
    monkeypatch.setattr(internal_audits_routes, "get_data_integrity_audit_run_status", lambda run_id: None)

    response = client.get("/api/internal/audits/data-integrity/runs/missing")

    assert response.status_code == 404
    assert response.json()["detail"] == "audit run not found"


def test_internal_audit_routes_require_authentication() -> None:
    client = _create_client()

    response = client.post("/api/internal/audits/data-integrity/runs", json={})

    assert response.status_code == 401
