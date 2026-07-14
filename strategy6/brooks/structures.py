"""Brooks failure structures around Strategy6 key support."""
from __future__ import annotations

from strategy6.brooks.compact import _near_support
from strategy6.brooks.metrics import bar_metrics, find_swing_lows
from strategy6.brooks.models import BrooksSellingPressureResult, BrooksStructureResult
from strategy6.models import Strategy6Support


def analyze_brooks_structures(
    rows: list[dict],
    support: Strategy6Support,
    selling: BrooksSellingPressureResult,
    *,
    compact_structure_type: str,
    atr14: float,
    tail_volume_ratio: float,
    config: dict,
) -> BrooksStructureResult:
    result = BrooksStructureResult()
    if not rows or support.key_support_price <= 0:
        result.risk_tags.append("BROOKS_STRUCTURE_DATA_INSUFFICIENT")
        return result

    _detect_recent_lows(rows, support, selling, atr14, config, result)
    _detect_failed_breakout(rows, support, selling, atr14, config, result)
    if selling.bear_follow_through_failed:
        result.bear_follow_through_failed = True
        result.bear_follow_through_failed_date = selling.bear_follow_through_failed_date
        result.setup_types.append("BEAR_FOLLOW_THROUGH_FAILED")
    if (
        compact_structure_type == "COMPACT_ORDERLY"
        and selling.exhausted
        and tail_volume_ratio <= float(config["volume_dry"]["tail_volume_ratio_max"])
        and _near_support(rows, support, atr14, config["support"])
    ):
        result.orderly_compression_at_support = True
        result.setup_types.append("ORDERLY_COMPRESSION_AT_SUPPORT")
    result.setup_types = list(dict.fromkeys(result.setup_types))
    return result


def _detect_recent_lows(
    rows: list[dict],
    support: Strategy6Support,
    selling: BrooksSellingPressureResult,
    atr14: float,
    config: dict,
    result: BrooksStructureResult,
) -> None:
    cfg = config["second_entry"]
    if not cfg["enabled"]:
        return
    points = find_swing_lows(rows)
    if len(points) < 2:
        return
    pair = None
    for first, second in zip(points[:-1], points[1:]):
        separation = second.index - first.index
        if int(cfg["min_separation_days"]) <= separation <= int(cfg["max_separation_days"]):
            pair = (first, second)
    if pair is None:
        return
    first, second = pair
    result.first_recent_low_date = first.date
    result.first_recent_low_price = first.price
    result.second_recent_low_date = second.date
    result.second_recent_low_price = second.price
    result.second_low_similarity = round(second.price / first.price - 1, 6) if first.price > 0 else None
    tolerance = float(cfg["low_similarity_tolerance"])
    both_near_support = all(
        _price_near_support(point.price, support, atr14, config["support"])
        for point in (first, second)
    )
    similar = second.price >= first.price * (1 - tolerance)
    second_row = rows[second.index]
    signal_metrics = bar_metrics(second_row)
    no_follow_through = selling.exhausted and selling.bear_follow_through_count == 0
    reclaimed = float(second_row.get("close") or 0) >= float(support.support_zone_low or support.key_support_price)
    result.micro_double_bottom = both_near_support and similar and reclaimed and no_follow_through
    if result.micro_double_bottom:
        result.setup_types.append("MICRO_DOUBLE_BOTTOM")
    result.second_entry_long_ready = bool(
        result.micro_double_bottom
        and signal_metrics.valid
        and (signal_metrics.close_position or 0) >= float(cfg["signal_bar_close_position_min"])
        and (signal_metrics.body_ratio or 1) <= float(cfg["signal_bar_max_body_ratio"])
    )
    if result.second_entry_long_ready:
        result.second_entry_signal_date = second.date
        result.second_entry_signal_high = float(second_row.get("high") or 0)
        result.second_entry_trigger_price = result.second_entry_signal_high
        result.setup_types.append("SECOND_ENTRY_LONG_READY")


def _detect_failed_breakout(
    rows: list[dict],
    support: Strategy6Support,
    selling: BrooksSellingPressureResult,
    atr14: float,
    config: dict,
    result: BrooksStructureResult,
) -> None:
    cfg = config["failed_breakout"]
    if not cfg["enabled"]:
        return
    key = float(support.key_support_price)
    recovery_days = int(cfg["recovery_days"])
    max_distance = float(atr14) * float(cfg["max_break_distance_atr"])
    selected_event: tuple[tuple[int, int], str, str] | None = None
    for index, row in enumerate(rows[:-1]):
        low = float(row.get("low") or 0)
        close = float(row.get("close") or 0)
        broke = min(low, close) < key
        if not broke or key - min(low, close) > max_distance:
            continue
        recovery = rows[index + 1:index + recovery_days + 1]
        reclaim = next(
            (item for item in recovery if float(item.get("close") or 0) >= key),
            None,
        )
        if reclaim is not None and selling.exhausted and selling.bear_follow_through_count == 0:
            priority = (int(close < key), index)
            event = (priority, str(row.get("date") or ""), str(reclaim.get("date") or ""))
            if selected_event is None or event[0] > selected_event[0]:
                selected_event = event
    if selected_event is not None:
        result.failed_bear_breakout = True
        result.failed_bear_breakout_date = selected_event[1]
        result.reclaim_date = selected_event[2]
    if result.failed_bear_breakout:
        result.setup_types.append("FAILED_BEAR_BREAKOUT")


def _price_near_support(price: float, support: Strategy6Support, atr14: float, config: dict) -> bool:
    limit = max(
        float(support.key_support_price) * float(config["support_distance_pct"]),
        float(atr14) * float(config["support_distance_atr"]),
    )
    return abs(price - float(support.key_support_price)) <= limit
