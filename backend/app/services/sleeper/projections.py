"""Estimated weekly totals from available Sleeper projection components."""

import math


def projected_points(stats: dict, scoring: dict) -> float | None:
    # Some rows only contain draft-position metadata, not a weekly projection.
    if not any(key in scoring for key in stats) and not any(stats.get(key) == 0 for key in ("pts_ppr", "pts_half_ppr", "pts_std")):
        return None
    total = 0.0
    for key, weight in scoring.items():
        value = stats.get(key, 0)
        if not isinstance(weight, (int, float)) or not isinstance(value, (int, float)):
            return None
        if not math.isfinite(weight) or not math.isfinite(value):
            return None
        total += value * weight
    return total


def starter_projection(player_ids: list[str], projections: dict[str, dict], scoring: dict) -> float | None:
    if not player_ids or not scoring:
        return None
    total = 0.0
    for player_id in player_ids:
        if player_id == "0":
            continue
        stats = projections.get(player_id)
        if not isinstance(stats, dict):
            return None
        points = projected_points(stats, scoring)
        if points is None:
            return None
        total += points
    return round(total, 2)
