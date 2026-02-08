from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from secrets import token_urlsafe

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _normalize_password(password: str) -> str:
    raw = password.encode("utf-8")
    if len(raw) <= 72:
        return password
    return raw[:72].decode("utf-8", "ignore")


def get_password_hash(password: str) -> str:
    return _pwd_context.hash(_normalize_password(password))


def verify_password(plain_password: str, password_hash: str) -> bool:
    return _pwd_context.verify(_normalize_password(plain_password), password_hash)


def create_access_token(subject: str) -> tuple[str, int]:
    now = datetime.now(timezone.utc)
    expires_delta = timedelta(minutes=settings.access_token_expires_minutes)
    expire = now + expires_delta
    payload = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, int(expires_delta.total_seconds())


def decode_access_token(token: str) -> dict[str, object]:
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


def create_refresh_token() -> str:
    return token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def refresh_token_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expires_days)


class TokenDecodeError(Exception):
    pass


def safe_decode_access_token(token: str) -> dict[str, object]:
    try:
        return decode_access_token(token)
    except JWTError as exc:
        raise TokenDecodeError(str(exc)) from exc
