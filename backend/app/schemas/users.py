from __future__ import annotations

from pydantic import BaseModel, Field


class UserCreateRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=6)
    display_name: str | None = None


class UserUpdateRequest(BaseModel):
    display_name: str | None = None
    status: str | None = None


class UserResetPasswordRequest(BaseModel):
    password: str = Field(..., min_length=6)


class UserResponse(BaseModel):
    id: str
    username: str
    display_name: str | None = None
    status: str
    created_at: object | None = None
    updated_at: object | None = None
    last_login_at: object | None = None


class UsersListResponse(BaseModel):
    items: list[UserResponse]
    total: int
