from __future__ import annotations

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query, status

from app.data.mongo_users import (
    create_user,
    get_user_by_id,
    get_user_by_username,
    list_users,
    serialize_user,
    serialize_users,
    update_password,
    update_user,
)
from app.schemas.users import (
    UserCreateRequest,
    UserResetPasswordRequest,
    UserUpdateRequest,
    UsersListResponse,
    UserResponse,
)

router = APIRouter()


@router.get("/users", response_model=UsersListResponse)
def list_users_route(
    search: str | None = Query(default=None),
    status_value: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
) -> UsersListResponse:
    items, total = list_users(search=search, status=status_value, page=page, page_size=page_size)
    return UsersListResponse(items=serialize_users(items), total=total)


@router.get("/users/{user_id}", response_model=UserResponse)
def get_user(user_id: str) -> UserResponse:
    try:
        obj_id = ObjectId(user_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user = get_user_by_id(obj_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserResponse(**serialize_user(user))


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user_route(payload: UserCreateRequest) -> UserResponse:
    existing = get_user_by_username(payload.username)
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")
    user_id = create_user(
        username=payload.username,
        password=payload.password,
        display_name=payload.display_name,
        status="active",
    )
    user = get_user_by_id(user_id)
    return UserResponse(**serialize_user(user))


@router.patch("/users/{user_id}", response_model=UserResponse)
def update_user_route(user_id: str, payload: UserUpdateRequest) -> UserResponse:
    try:
        obj_id = ObjectId(user_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if payload.status is not None and payload.status not in {"active", "disabled"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid status")
    user = update_user(obj_id, display_name=payload.display_name, status=payload.status)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserResponse(**serialize_user(user))


@router.post("/users/{user_id}/reset-password", response_model=UserResponse)
def reset_password(user_id: str, payload: UserResetPasswordRequest) -> UserResponse:
    try:
        obj_id = ObjectId(user_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user = update_password(obj_id, payload.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserResponse(**serialize_user(user))
