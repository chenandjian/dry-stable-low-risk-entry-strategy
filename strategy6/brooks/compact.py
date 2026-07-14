"""Interpret shared compact K-line metrics for Brooks price action."""
from __future__ import annotations

from strategy6.brooks.metrics import bar_metrics, count_direction_changes
from strategy6.brooks.models import (
    BrooksCompactStructureResult,
    BrooksContextResult,
    BrooksSellingPressureResult,
)
from strategy6.models import Strategy6CompactKline, Strategy6Support


def classify_compact_structure(
    rows: list[dict],
    compact: Strategy6CompactKline,
    context: BrooksContextResult,
    support: Strategy6Support,
    selling: BrooksSellingPressureResult,
    *,
    atr14: float,
    config: dict,
) -> BrooksCompactStructureResult:
    cfg = config["compact_structure"]
    result = BrooksCompactStructureResult()
    if not cfg["enabled"] or not compact.enabled or not compact.passed:
        return result

    # More than three direction changes require at least six bars. Price
    # stability still uses its configured five-bar window independently.
    window_days = max(
        int(config["price_stability"]["compact_window_days"]),
        int(cfg["max_direction_changes"]) + 3,
    )
    window = rows[-window_days:]
    result.direction_change_count = count_direction_changes(window)
    for row in window:
        metrics = bar_metrics(row)
        if metrics.valid and max(
            metrics.upper_shadow_ratio or 0,
            metrics.lower_shadow_ratio or 0,
        ) >= float(cfg["long_shadow_ratio_min"]):
            result.long_shadow_bar_count += 1

    if context.context_type == "BEAR_CONTEXT" or (
        context.lower_high_low_sequence_count > int(config["context"]["max_lower_high_low_sequence"])
        and not selling.exhausted
    ):
        result.structure_type = "COMPACT_BEARISH"
        result.risk_tags.append("BROOKS_COMPACT_BEARISH")
        return result

    result.barb_wire_risk = (
        result.direction_change_count > int(cfg["max_direction_changes"])
        and result.long_shadow_bar_count > int(cfg["max_long_shadow_bar_count"])
    )
    if result.barb_wire_risk:
        result.structure_type = "BARB_WIRE"
        result.risk_tags.append("BARB_WIRE_RISK")
        return result

    near_support = _near_support(rows, support, atr14, config["support"])
    if context.passed and selling.exhausted and near_support:
        result.structure_type = "COMPACT_ORDERLY"
        result.reasons.append("BROOKS_COMPACT_ORDERLY")
    else:
        result.structure_type = "COMPACT_NEUTRAL"
        result.risk_tags.append("BROOKS_COMPACT_NEUTRAL")
    return result


def _near_support(rows: list[dict], support: Strategy6Support, atr14: float, config: dict) -> bool:
    if not rows or support.key_support_price <= 0:
        return False
    current = float(rows[-1].get("close") or 0)
    limit = max(
        float(support.key_support_price) * float(config["support_distance_pct"]),
        float(atr14) * float(config["support_distance_atr"]),
    )
    return abs(current - float(support.key_support_price)) <= limit
