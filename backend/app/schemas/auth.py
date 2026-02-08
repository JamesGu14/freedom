from __future__ import annotations

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class MeResponse(BaseModel):
    id: str
    username: str
    display_name: str | None = None
    status: str
    created_at: object | None = None
    updated_at: object | None = None
    last_login_at: object | None = None
