from __future__ import annotations

from typing import Any


def score_to_slot_weight(score: float, slot_weight: float = 0.2) -> float:
    if score >= 90:
        return slot_weight * 1.0
    if score >= 85:
        return slot_weight * 0.75
    if score >= 80:
        return slot_weight * 0.5
    if score >= 75:
        return slot_weight * 0.25
    return 0.0


def calc_target_weight(
    *,
    score: float,
    market_exposure: float,
    slot_weight: float,
    sector_weight: float = 1.0,
) -> float:
    base = score_to_slot_weight(score, slot_weight=slot_weight)
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

