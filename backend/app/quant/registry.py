from __future__ import annotations

from app.quant.base import MultiFactorV1Strategy, StrategyProtocol


_REGISTRY: dict[str, type[StrategyProtocol]] = {
    MultiFactorV1Strategy.key: MultiFactorV1Strategy,
}


def list_registered_strategies() -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for key, cls in sorted(_REGISTRY.items(), key=lambda x: x[0]):
        items.append({"key": key, "name": getattr(cls, "name", key)})
    return items


def load_strategy(key: str) -> StrategyProtocol:
    normalized = (key or "").strip()
    if not normalized:
        normalized = MultiFactorV1Strategy.key
    strategy_cls = _REGISTRY.get(normalized)
    if not strategy_cls:
        raise ValueError(f"strategy not found: {key}")
    return strategy_cls()

