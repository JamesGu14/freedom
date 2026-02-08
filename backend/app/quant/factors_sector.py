from __future__ import annotations

from collections import defaultdict
from typing import Any


def _score_from_rank(rank: Any, rank_total: Any) -> float:
    try:
        rank_value = float(rank)
        total_value = float(rank_total)
    except (TypeError, ValueError):
        return 50.0
    if total_value <= 1:
        return 50.0
    normalized = 1.0 - (rank_value - 1.0) / (total_value - 1.0)
    return max(min(normalized * 100.0, 100.0), 0.0)


def _score_from_pct_change(value: Any) -> float:
    try:
        pct = float(value)
    except (TypeError, ValueError):
        return 50.0
    # Map around [-5%, +5%] to [0, 100]
    normalized = (pct + 5.0) / 10.0
    normalized = max(min(normalized, 1.0), 0.0)
    return normalized * 100.0


def build_sector_strength_map(rows: list[dict[str, Any]]) -> dict[str, float]:
    if not rows:
        return {}

    grouped: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        rank_score = _score_from_rank(row.get("rank"), row.get("rank_total"))
        pct_score = _score_from_pct_change(row.get("pct_change"))
        score = rank_score * 0.7 + pct_score * 0.3
        grouped[name].append(score)

    result: dict[str, float] = {}
    for name, values in grouped.items():
        if not values:
            continue
        result[name] = sum(values) / len(values)
    return result

