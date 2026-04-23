from __future__ import annotations

import json
import logging
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

_redis_client = None
_reported_failures: set[str] = set()


def get_redis():
    global _redis_client
    if _redis_client is not None:
        return _redis_client

    import redis as redis_lib
    _redis_client = redis_lib.Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
    )
    return _redis_client


def _log_first(op: str, exc: BaseException) -> None:
    """Log one warning per (op, exception-type); suppress subsequent duplicates."""
    kind = type(exc).__name__
    signature = f"{op}:{kind}"
    if signature in _reported_failures:
        logger.debug("cache %s failed again (%s): %s", op, kind, exc)
        return
    _reported_failures.add(signature)
    logger.warning(
        "cache %s failed (%s): %s — further errors of this kind will log at DEBUG",
        op, kind, exc,
    )


def cache_get(key: str) -> Any | None:
    try:
        r = get_redis()
        data = r.get(key)
        if data:
            return json.loads(data)
    except Exception as exc:
        _log_first("get", exc)
    return None


def cache_set(key: str, value: Any, ttl_seconds: int = 86400) -> bool:
    try:
        r = get_redis()
        r.setex(key, ttl_seconds, json.dumps(value, default=str))
        return True
    except Exception as exc:
        _log_first("set", exc)
        return False


def cache_delete(key: str) -> bool:
    try:
        r = get_redis()
        r.delete(key)
        return True
    except Exception as exc:
        _log_first("delete", exc)
        return False


def cache_delete_pattern(pattern: str) -> int:
    try:
        r = get_redis()
        keys = list(r.scan_iter(match=pattern))
        if keys:
            return r.delete(*keys)
        return 0
    except Exception as exc:
        _log_first("delete_pattern", exc)
        return 0
