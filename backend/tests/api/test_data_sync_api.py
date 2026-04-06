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


def test_data_sync_jobs_route_is_removed() -> None:
    client = _create_client()

    response = client.post("/api/data-sync/jobs", json={"start_date": "20260313", "end_date": "20260313"})

    assert response.status_code == 404

