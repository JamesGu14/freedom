from __future__ import annotations

import logging

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.data.duckdb_store import get_connection
from app.data.mongo import get_mongo_client
from app.data.redis_client import get_redis_client

logger = logging.getLogger(__name__)

router = APIRouter()


def _check_mongodb() -> tuple[bool, str]:
    try:
        client = get_mongo_client()
        _ = client.admin.command("ping")
        return True, "connected"
    except Exception as exc:
        logger.warning("Health check: MongoDB connection failed: %s", exc)
        return False, str(exc)


def _check_duckdb() -> tuple[bool, str]:
    try:
        with get_connection(read_only=True) as con:
            _ = con.execute("SELECT 1").fetchone()
        return True, "connected"
    except Exception as exc:
        logger.warning("Health check: DuckDB connection failed: %s", exc)
        return False, str(exc)


def _check_redis() -> tuple[bool, str]:
    try:
        client = get_redis_client()
        if client is None:
            return True, "disabled"
        client.ping()
        return True, "connected"
    except Exception as exc:
        logger.warning("Health check: Redis connection failed: %s", exc)
        return False, str(exc)


@router.get("/health")
def health_check() -> JSONResponse:
    mongo_ok, mongo_status = _check_mongodb()
    duckdb_ok, duckdb_status = _check_duckdb()
    redis_ok, redis_status = _check_redis()

    all_ok = mongo_ok and duckdb_ok and redis_ok
    status_code = status.HTTP_200_OK if all_ok else status.HTTP_503_SERVICE_UNAVAILABLE

    response_data = {
        "status": "ok" if all_ok else "degraded",
        "dependencies": {
            "mongodb": {"status": "ok" if mongo_ok else "error", "detail": mongo_status},
            "duckdb": {"status": "ok" if duckdb_ok else "error", "detail": duckdb_status},
            "redis": {"status": "ok" if redis_ok else "error", "detail": redis_status},
        },
    }

    return JSONResponse(content=response_data, status_code=status_code)
