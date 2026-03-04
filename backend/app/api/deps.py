from __future__ import annotations

import secrets

from bson import ObjectId
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings
from app.core.security import TokenDecodeError, safe_decode_access_token
from app.data.mongo_users import get_user_by_id

_bearer_scheme = HTTPBearer(auto_error=False)


def _get_user_from_access_token(token: str) -> dict[str, object]:
    try:
        payload = safe_decode_access_token(token)
    except TokenDecodeError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    subject = payload.get("sub")
    if not subject:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    try:
        user_id = ObjectId(str(subject))
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if user.get("status") == "disabled":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User disabled")
    return user


def _is_internal_api_token(token: str) -> bool:
    configured = str(settings.internal_api_token or "").strip()
    if not configured or not token:
        return False
    return secrets.compare_digest(token, configured)


def _build_internal_api_user() -> dict[str, object]:
    return {
        "_id": "internal-api-token",
        "username": "internal",
        "display_name": "internal-api-token",
        "status": "active",
        "auth_type": "internal_api_token",
    }


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> dict[str, object]:
    if credentials is None or not credentials.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    token = credentials.credentials
    if _is_internal_api_token(token):
        return _build_internal_api_user()
    return _get_user_from_access_token(token)


def require_admin_user(
    current_user: dict[str, object] = Depends(get_current_user),
) -> dict[str, object]:
    if str(current_user.get("auth_type") or "") == "internal_api_token":
        return current_user
    username = str(current_user.get("username") or "").strip().lower()
    if username not in {"admin", "james"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin required")
    return current_user
