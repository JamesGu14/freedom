from __future__ import annotations

from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.api import deps


def test_get_current_user_uses_auth_verify_url_when_configured(monkeypatch) -> None:
    monkeypatch.setattr(deps.settings, "auth_verify_url", "http://127.0.0.1:13900/v1/internal/verify")
    monkeypatch.setattr(
        deps,
        "_verify_with_personal_authenticator",
        lambda token: {
            "_id": 1,
            "username": "james",
            "display_name": "james",
            "status": "active",
            "auth_type": "personal_authenticator",
            "roles": ["admin"],
            "created_at": None,
            "updated_at": None,
            "last_login_at": None,
        },
    )

    user = deps._get_user_from_credentials(HTTPAuthorizationCredentials(scheme="Bearer", credentials="token"))

    assert user["username"] == "james"
    assert user["roles"] == ["admin"]


def test_get_current_user_requires_authorization_header() -> None:
    try:
        deps._get_user_from_credentials(None)
    except HTTPException as exc:
        assert exc.status_code == 401
        assert exc.detail == "Missing token"
    else:  # pragma: no cover
        raise AssertionError("expected HTTPException")


def test_get_current_user_does_not_fallback_to_local_jwt_when_verify_rejects(monkeypatch) -> None:
    monkeypatch.setattr(deps.settings, "auth_verify_url", "http://127.0.0.1:13900/v1/internal/verify")

    def reject_verify(token: str) -> dict[str, object]:
        raise HTTPException(status_code=401, detail="Invalid token")

    monkeypatch.setattr(deps, "_verify_with_personal_authenticator", reject_verify)
    monkeypatch.setattr(
        deps,
        "_get_user_from_access_token",
        lambda token: {
            "_id": 1,
            "username": "james",
            "display_name": "james",
            "status": "active",
            "auth_type": "local_jwt",
            "roles": ["admin"],
        },
    )

    try:
        deps._get_user_from_credentials(HTTPAuthorizationCredentials(scheme="Bearer", credentials="token"))
    except HTTPException as exc:
        assert exc.status_code == 401
        assert exc.detail == "Invalid token"
    else:  # pragma: no cover
        raise AssertionError("expected HTTPException")


def test_get_current_user_rejects_internal_api_token_after_migration(monkeypatch) -> None:
    monkeypatch.setattr(deps.settings, "auth_verify_url", "http://127.0.0.1:13900/v1/internal/verify")
    monkeypatch.setattr(deps.settings, "internal_api_token", "legacy-token")

    def reject_verify(token: str) -> dict[str, object]:
        raise HTTPException(status_code=401, detail="Invalid token")

    monkeypatch.setattr(deps, "_verify_with_personal_authenticator", reject_verify)

    try:
        deps._get_user_from_credentials(
            HTTPAuthorizationCredentials(scheme="Bearer", credentials="legacy-token")
        )
    except HTTPException as exc:
        assert exc.status_code == 401
        assert exc.detail == "Invalid token"
    else:  # pragma: no cover
        raise AssertionError("expected HTTPException")


def test_require_admin_user_requires_admin_role() -> None:
    try:
        deps.require_admin_user(
            {
                "_id": 1,
                "username": "james",
                "display_name": "james",
                "status": "active",
                "auth_type": "personal_authenticator",
                "roles": ["user"],
            }
        )
    except HTTPException as exc:
        assert exc.status_code == 403
        assert exc.detail == "Admin required"
    else:  # pragma: no cover
        raise AssertionError("expected HTTPException")
