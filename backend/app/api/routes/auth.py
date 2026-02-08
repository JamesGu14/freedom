from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, Response, status, Depends

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_refresh_token,
    refresh_token_expiry,
    verify_password,
)
from app.data.mongo_refresh_tokens import (
    create_refresh_token_record,
    find_refresh_token,
    is_refresh_token_valid,
    revoke_refresh_token,
)
from app.data.mongo_users import get_user_by_username, get_user_by_id, serialize_user, touch_last_login
from app.schemas.auth import LoginRequest, TokenResponse, MeResponse

router = APIRouter()


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key="refresh_token",
        value=token,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite=settings.auth_cookie_samesite,
        max_age=settings.refresh_token_expires_days * 24 * 60 * 60,
        domain=settings.auth_cookie_domain or None,
        path="/api/auth",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key="refresh_token",
        domain=settings.auth_cookie_domain or None,
        path="/api/auth",
    )


@router.post("/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, response: Response) -> TokenResponse:
    user = get_user_by_username(payload.username)
    if not user or not verify_password(payload.password, str(user.get("password_hash"))):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if user.get("status") == "disabled":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User disabled")

    access_token, expires_in = create_access_token(str(user.get("_id")))
    refresh_token = create_refresh_token()
    token_hash = hash_refresh_token(refresh_token)
    create_refresh_token_record(
        user_id=user.get("_id"),
        token_hash=token_hash,
        expires_at=refresh_token_expiry(),
    )
    _set_refresh_cookie(response, refresh_token)
    touch_last_login(user.get("_id"))
    return TokenResponse(access_token=access_token, expires_in=expires_in)


@router.post("/auth/refresh", response_model=TokenResponse)
def refresh(request: Request, response: Response) -> TokenResponse:
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing refresh token")
    token_hash = hash_refresh_token(refresh_token)
    record = find_refresh_token(token_hash)
    if not record or not is_refresh_token_valid(record):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    user = get_user_by_id(record.get("user_id"))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if user.get("status") == "disabled":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User disabled")

    revoke_refresh_token(token_hash)
    new_refresh = create_refresh_token()
    create_refresh_token_record(
        user_id=record.get("user_id"),
        token_hash=hash_refresh_token(new_refresh),
        expires_at=refresh_token_expiry(),
    )
    _set_refresh_cookie(response, new_refresh)

    access_token, expires_in = create_access_token(str(record.get("user_id")))
    return TokenResponse(access_token=access_token, expires_in=expires_in)


@router.post("/auth/logout")
def logout(request: Request, response: Response) -> dict[str, bool]:
    refresh_token = request.cookies.get("refresh_token")
    if refresh_token:
        revoke_refresh_token(hash_refresh_token(refresh_token))
    _clear_refresh_cookie(response)
    return {"ok": True}


@router.get("/auth/me", response_model=MeResponse)
def me(current_user: dict[str, object] = Depends(get_current_user)) -> MeResponse:
    return MeResponse(**serialize_user(current_user))
