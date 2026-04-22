from __future__ import annotations

import json
import logging
import socket
from urllib import error as urllib_error
from urllib import request as urllib_request

from bson import ObjectId
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings
from app.core.security import TokenDecodeError, safe_decode_access_token
from app.data.mongo_users import get_user_by_id

logger = logging.getLogger(__name__)

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


def _build_personal_auth_user(payload: dict[str, object]) -> dict[str, object]:
    username = str(payload.get("username") or "").strip()
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    roles_raw = payload.get("roles")
    roles = [str(item).strip() for item in roles_raw if str(item).strip()] if isinstance(roles_raw, list) else []
    return {
        "_id": payload.get("userId"),
        "username": username,
        "display_name": username,
        "status": "active",
        "auth_type": "personal_authenticator",
        "roles": roles,
        "created_at": None,
        "updated_at": None,
        "last_login_at": None,
    }


def _verify_with_personal_authenticator(token: str) -> dict[str, object]:
    verify_url = str(settings.auth_verify_url or "").strip()
    if not verify_url:
        raise RuntimeError("AUTH_VERIFY_URL is not configured")

    req = urllib_request.Request(
        verify_url,
        method="POST",
        headers={"Authorization": f"Bearer {token}"},
    )
    opener = urllib_request.build_opener(urllib_request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=settings.auth_verify_timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib_error.HTTPError as exc:
        if exc.code in {status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN}:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication service unavailable",
        ) from exc
    except (urllib_error.URLError, TimeoutError, socket.timeout, OSError) as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication service unavailable",
        ) from exc

    return _build_personal_auth_user(payload)


def _get_user_from_credentials(credentials: HTTPAuthorizationCredentials | None) -> dict[str, object]:
    if credentials is None or not credentials.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")

    token = credentials.credentials
    verify_url = str(settings.auth_verify_url or "").strip()
    if not verify_url:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication service unavailable",
        )
    return _verify_with_personal_authenticator(token)


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> dict[str, object]:
    user = _get_user_from_credentials(credentials)
    try:
        from app.data.mongo_api_audit import insert_api_audit_log
        insert_api_audit_log(
            user_id=str(user.get("_id") or ""),
            username=str(user.get("username") or ""),
            endpoint=request.url.path,
            method=request.method,
            status_code=200,
        )
    except Exception:
        logger.debug("api audit log write failed", exc_info=True)
    return user


def require_admin_user(
    current_user: dict[str, object] = Depends(get_current_user),
) -> dict[str, object]:
    roles = current_user.get("roles")
    if isinstance(roles, list) and any(str(role).strip().lower() == "admin" for role in roles):
        return current_user
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin required")


def get_current_username(
    current_user: dict[str, object] = Depends(get_current_user),
) -> str:
    return str(current_user.get("username") or "").strip()
