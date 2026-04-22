from __future__ import annotations

import json
from typing import Any

from app.core.config import settings

_redis_client = None


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


def cache_get(key: str) -> Any | None:
    try:
        r = get_redis()
        data = r.get(key)
        if data:
            return json.loads(data)
    except Exception:
        pass
    return None


def cache_set(key: str, value: Any, ttl_seconds: int = 86400) -> bool:
    try:
        r = get_redis()
        r.setex(key, ttl_seconds, json.dumps(value, default=str))
        return True
    except Exception:
        return False


def cache_delete(key: str) -> bool:
    try:
        r = get_redis()
        r.delete(key)
        return True
    except Exception:
        return False


def cache_delete_pattern(pattern: str) -> int:
    try:
        r = get_redis()
        keys = list(r.scan_iter(match=pattern))
        if keys:
            return r.delete(*keys)
        return 0
    except Exception:
        return 0
