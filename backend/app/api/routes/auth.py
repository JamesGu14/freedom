from __future__ import annotations

import json
import socket
from urllib import error as urllib_error
from urllib import request as urllib_request

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.deps import _verify_with_personal_authenticator, get_current_user
from app.core.config import settings
from app.data.mongo_users import serialize_user
from app.schemas.auth import LoginRequest, LogoutRequest, MeResponse, RefreshRequest, TokenResponse

router = APIRouter()


def _build_auth_login_url() -> str:
    configured = str(settings.auth_login_url or "").strip()
    if configured:
        return configured
    verify_url = str(settings.auth_verify_url or "").strip()
    if verify_url.endswith("/v1/internal/verify"):
        return f"{verify_url[:-len('/v1/internal/verify')]}/v1/auth/login"
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Authentication service unavailable",
    )


def _build_auth_refresh_url() -> str:
    configured = str(settings.auth_refresh_url or "").strip()
    if configured:
        return configured
    verify_url = str(settings.auth_verify_url or "").strip()
    if verify_url.endswith("/v1/internal/verify"):
        return f"{verify_url[:-len('/v1/internal/verify')]}/v1/auth/refresh"
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Authentication service unavailable",
    )


def _build_auth_logout_url() -> str:
    configured = str(settings.auth_logout_url or "").strip()
    if configured:
        return configured
    verify_url = str(settings.auth_verify_url or "").strip()
    if verify_url.endswith("/v1/internal/verify"):
        return f"{verify_url[:-len('/v1/internal/verify')]}/v1/auth/logout"
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Authentication service unavailable",
    )


def _extract_error_detail(exc: urllib_error.HTTPError) -> str:
    try:
        body = exc.read().decode("utf-8")
        payload = json.loads(body)
    except Exception:
        return ""
    detail = payload.get("detail") if isinstance(payload, dict) else ""
    return str(detail or "").strip()


def _login_with_personal_authenticator(username: str, password: str) -> dict[str, str]:
    body = json.dumps({"username": username, "password": password}).encode("utf-8")
    req = urllib_request.Request(
        _build_auth_login_url(),
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    opener = urllib_request.build_opener(urllib_request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=settings.auth_verify_timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib_error.HTTPError as exc:
        if exc.code in {status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN}:
            detail = _extract_error_detail(exc) or "Invalid credentials"
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail) from exc
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication service unavailable",
        ) from exc
    except (urllib_error.URLError, TimeoutError, socket.timeout, OSError) as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication service unavailable",
        ) from exc

    access_token = str(payload.get("access_token") or "").strip()
    refresh_token = str(payload.get("refresh_token") or "").strip()
    token_type = str(payload.get("token_type") or "bearer").strip() or "bearer"
    if not access_token or not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication service unavailable",
        )
    _verify_with_personal_authenticator(access_token)
    return {"access_token": access_token, "refresh_token": refresh_token, "token_type": token_type}


def _refresh_with_personal_authenticator(refresh_token: str) -> dict[str, str]:
    if not refresh_token.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="refresh_token required")

    body = json.dumps({"refresh_token": refresh_token.strip()}).encode("utf-8")
    req = urllib_request.Request(
        _build_auth_refresh_url(),
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    opener = urllib_request.build_opener(urllib_request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=settings.auth_verify_timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib_error.HTTPError as exc:
        if exc.code in {status.HTTP_400_BAD_REQUEST, status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN}:
            detail = _extract_error_detail(exc) or (
                "refresh_token required" if exc.code == status.HTTP_400_BAD_REQUEST else "Invalid refresh token"
            )
            raise HTTPException(status_code=exc.code, detail=detail) from exc
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication service unavailable",
        ) from exc
    except (urllib_error.URLError, TimeoutError, socket.timeout, OSError) as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication service unavailable",
        ) from exc

    access_token = str(payload.get("access_token") or "").strip()
    next_refresh_token = str(payload.get("refresh_token") or "").strip()
    token_type = str(payload.get("token_type") or "bearer").strip() or "bearer"
    if not access_token or not next_refresh_token:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication service unavailable",
        )
    _verify_with_personal_authenticator(access_token)
    return {"access_token": access_token, "refresh_token": next_refresh_token, "token_type": token_type}


def _logout_with_personal_authenticator(refresh_token: str | None) -> None:
    body = json.dumps({"refresh_token": (refresh_token or "").strip() or None}).encode("utf-8")
    req = urllib_request.Request(
        _build_auth_logout_url(),
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    opener = urllib_request.build_opener(urllib_request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=settings.auth_verify_timeout_seconds):
            return
    except urllib_error.HTTPError as exc:
        if exc.code in {status.HTTP_400_BAD_REQUEST, status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN}:
            detail = _extract_error_detail(exc) or "Logout failed"
            raise HTTPException(status_code=exc.code, detail=detail) from exc
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication service unavailable",
        ) from exc
    except (urllib_error.URLError, TimeoutError, socket.timeout, OSError) as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication service unavailable",
        ) from exc


def _serialize_current_user(current_user: dict[str, object]) -> dict[str, object]:
    payload = serialize_user(current_user)
    roles = current_user.get("roles")
    payload["roles"] = [str(role).strip() for role in roles if str(role).strip()] if isinstance(roles, list) else []
    return payload


@router.post("/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, response: Response) -> TokenResponse:
    del response
    data = _login_with_personal_authenticator(payload.username, payload.password)
    return TokenResponse(**data)


@router.post("/auth/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, response: Response) -> TokenResponse:
    del response
    data = _refresh_with_personal_authenticator(payload.refresh_token or "")
    return TokenResponse(**data)


@router.post("/auth/logout")
def logout(payload: LogoutRequest, response: Response) -> dict[str, bool]:
    del response
    _logout_with_personal_authenticator(payload.refresh_token)
    return {"ok": True}


@router.get("/auth/me", response_model=MeResponse)
def me(current_user: dict[str, object] = Depends(get_current_user)) -> MeResponse:
    return MeResponse(**_serialize_current_user(current_user))
