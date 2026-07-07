"""Shared Strategy4 topic-index buyability filters."""
from __future__ import annotations


def topic_index_context_passes_filters(context: dict, config: dict) -> bool:
    """Return whether an observed topic-index context is eligible for buyable candidates."""
    if not context.get("observed"):
        return True

    filters = config.get("topic_index_filters") or {}
    allowed_phases = filters.get("allowed_phases") or []
    phase = str(context.get("phase") or "")
    if allowed_phases and phase not in allowed_phases:
        return False

    if float(context.get("topic_index_trend_score") or 0) < float(filters.get("min_trend_score", 0)):
        return False
    if float(context.get("topic_index_breakout_score") or 0) < float(filters.get("min_breakout_score", 0)):
        return False
    if float(context.get("amount_ratio_5_20") or 0) < float(filters.get("min_amount_ratio_5_20", 0)):
        return False

    max_drawdown = filters.get("max_drawdown_from_high_20")
    if max_drawdown is not None:
        drawdown = abs(min(0.0, float(context.get("drawdown_from_high_20") or 0)))
        if drawdown > float(max_drawdown):
            return False
    return True
