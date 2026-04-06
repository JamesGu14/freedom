from __future__ import annotations

from typing import Any

from pymongo.errors import DuplicateKeyError

from app.data.mongo_backtest import (
    create_strategy_definition,
    create_strategy_version,
    get_strategy_definition,
    get_strategy_summary_item,
    list_latest_runs_by_strategy,
    list_strategy_definitions,
    list_strategy_versions,
    set_strategy_status,
    update_strategy_definition,
)
from app.quant.params_registry import normalize_strategy_key, validate_and_normalize_params
from app.quant.registry import is_registered_strategy, list_registered_strategies


def list_strategies(
    *,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    keyword: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    items, total = list_strategy_definitions(
        page=page,
        page_size=page_size,
        status=status,
        keyword=keyword,
    )
    latest_map = list_latest_runs_by_strategy()
    output = [get_strategy_summary_item(item, latest_map.get(str(item.get("strategy_id")))) for item in items]
    return output, total


def get_strategy(strategy_id: str) -> dict[str, Any] | None:
    return get_strategy_definition(strategy_id)


def create_strategy(
    *,
    name: str,
    strategy_key: str,
    description: str,
    owner: str,
    created_by: str,
) -> dict[str, Any]:
    if not name or not name.strip():
        raise ValueError("name is required")
    key = normalize_strategy_key(strategy_key)
    if not is_registered_strategy(key):
        raise ValueError(f"unsupported strategy_key: {strategy_key}")
    try:
        return create_strategy_definition(
            name=name.strip(),
            strategy_key=key,
            description=description or "",
            owner=owner or created_by or "",
            created_by=created_by or "",
            status="active",
        )
    except DuplicateKeyError as exc:
        raise ValueError("strategy name already exists") from exc


def update_strategy(
    *,
    strategy_id: str,
    name: str | None = None,
    description: str | None = None,
    owner: str | None = None,
) -> dict[str, Any]:
    if not get_strategy_definition(strategy_id):
        raise ValueError("strategy not found")
    try:
        result = update_strategy_definition(
            strategy_id=strategy_id,
            name=name,
            description=description,
            owner=owner,
        )
    except DuplicateKeyError as exc:
        raise ValueError("strategy name already exists") from exc
    if not result:
        raise ValueError("failed to update strategy")
    return result


def enable_strategy(strategy_id: str, enabled: bool) -> bool:
    return set_strategy_status(strategy_id, enabled=enabled)


def get_strategy_versions(strategy_id: str) -> list[dict[str, Any]]:
    return list_strategy_versions(strategy_id)


def create_version(
    *,
    strategy_id: str,
    params_snapshot: dict[str, Any] | None,
    code_ref: str,
    change_log: str,
    created_by: str,
    version: str | None = None,
) -> dict[str, Any]:
    strategy = get_strategy_definition(strategy_id)
    if not strategy:
        raise ValueError("strategy not found")
    payload = params_snapshot or {}
    if not isinstance(payload, dict):
        raise ValueError("params_snapshot must be object")
    strategy_key = normalize_strategy_key(strategy.get("strategy_key"))
    payload_key = str(payload.get("strategy_key") or "").strip()
    if payload_key and normalize_strategy_key(payload_key) != strategy_key:
        raise ValueError("params_snapshot.strategy_key does not match strategy definition strategy_key")
    normalized_params, params_schema_version = validate_and_normalize_params(strategy_key, payload)
    try:
        return create_strategy_version(
            strategy_id=strategy_id,
            strategy_key=strategy_key,
            params_snapshot=normalized_params,
            params_schema_version=params_schema_version,
            code_ref=code_ref or "",
            change_log=change_log or "",
            created_by=created_by or "",
            version=version,
        )
    except DuplicateKeyError as exc:
        raise ValueError("version already exists") from exc


def list_available_engine_strategies() -> list[dict[str, str]]:
    return list_registered_strategies()
