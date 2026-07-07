"""Strategy5 moving-average support status."""
from __future__ import annotations

from strategy5.models import Strategy5Support


def evaluate_support_status(
    *,
    close: float,
    ma5: float,
    ma10: float,
    ma20: float,
    ma50: float,
) -> Strategy5Support:
    """Evaluate support by priority: MA5, MA10, MA20, MA50, failed."""
    candidates = (
        ("SPRINT_MA5_SUPPORT", "MA5", ma5, 0.03),
        ("SPRINT_MA10_SUPPORT", "MA10", ma10, 0.04),
        ("SPRINT_MA20_SUPPORT", "MA20", ma20, 0.06),
        ("SPRINT_MA50_TESTING", "MA50", ma50, 0.08),
    )
    for status, label, value, max_dist in candidates:
        if close <= 0 or value <= 0:
            continue
        if label == "MA20":
            eligible = close >= value * 0.96
        elif label == "MA50":
            eligible = close >= value * 0.92
        else:
            eligible = close >= value
        dist = abs(close - value) / close
        if eligible and dist <= max_dist:
            return Strategy5Support(
                support_status=status,
                main_support_ma=label,
                main_support_price=round(value, 4),
                main_support_distance=round(dist, 6),
                support_score=_support_score(status, dist),
            )
    return Strategy5Support("SPRINT_FAILED")


def _support_score(status: str, dist: float) -> int:
    if status == "SPRINT_MA5_SUPPORT":
        if dist <= 0.01:
            return 10
        if dist <= 0.02:
            return 9
        return 8
    if status == "SPRINT_MA10_SUPPORT":
        if dist <= 0.01:
            return 9
        if dist <= 0.03:
            return 8
        return 7
    if status == "SPRINT_MA20_SUPPORT":
        if dist <= 0.02:
            return 7
        if dist <= 0.04:
            return 6
        return 5
    if status == "SPRINT_MA50_TESTING":
        return 4
    return 0
