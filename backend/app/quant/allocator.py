from __future__ import annotations

from typing import Any


def score_to_slot_weight(
    score: float,
    *,
    slot_weight: float = 0.2,
    buy_threshold: float = 75.0,
    score_ceiling: float = 100.0,
    min_scale: float = 0.6,
) -> float:
    if slot_weight <= 0:
        return 0.0
    if score < buy_threshold:
        return 0.0
    span = max(score_ceiling - buy_threshold, 1.0)
    progress = (score - buy_threshold) / span
    progress = max(min(progress, 1.0), 0.0)
    min_scale = max(min(min_scale, 1.0), 0.0)
    scale = min_scale + (1.0 - min_scale) * progress
    return slot_weight * scale


def calc_target_weight(
    *,
    score: float,
    market_exposure: float,
    slot_weight: float,
    buy_threshold: float = 75.0,
    score_ceiling: float = 100.0,
    slot_min_scale: float = 0.6,
    sector_weight: float = 1.0,
) -> float:
    base = score_to_slot_weight(
        score,
        slot_weight=slot_weight,
        buy_threshold=buy_threshold,
        score_ceiling=score_ceiling,
        min_scale=slot_min_scale,
    )
    if base <= 0:
        return 0.0
    return max(base * market_exposure * sector_weight, 0.0)


def calc_target_amount(
    *,
    total_equity: float,
    target_weight: float,
) -> float:
    if total_equity <= 0 or target_weight <= 0:
        return 0.0
    return total_equity * target_weight


def should_rotate(
    *,
    candidate_score: float,
    worst_score: float,
    worst_profit_pct: float,
    holding_days: int,
    rotate_score_delta: float,
    rotate_profit_ceiling: float,
    min_hold_days_before_rotate: int,
) -> bool:
    if candidate_score - worst_score < rotate_score_delta:
        return False
    if worst_profit_pct > rotate_profit_ceiling:
        return False
    if holding_days < min_hold_days_before_rotate:
        return False
    return True


def pick_worst_holding(holding_scores: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not holding_scores:
        return None
    return sorted(
        holding_scores,
        key=lambda x: (float(x.get("score") or 0.0), float(x.get("profit_pct") or 0.0)),
    )[0]
