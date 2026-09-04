"""Strategy6 body-support evidence and latest-bar pattern diagnostics."""
from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from strategy6.models import (
    Strategy6BodySupport,
    Strategy6LatestBarPattern,
    Strategy6Phase,
    Strategy6Support,
)


@dataclass
class _Pivot:
    index: int
    body_bottom: float
    low: float
    close: float
    atr: float
    recovery_atr: float
    low_rejection: bool
    volume_quality: bool


def evaluate_body_support(
    rows: list[dict],
    phase: Strategy6Phase,
    support: Strategy6Support,
    config: dict,
) -> Strategy6BodySupport:
    result = Strategy6BodySupport(enabled=bool(config.get("enabled", True)))
    if not result.enabled:
        result.status = "DISABLED"
        return result
    if not rows:
        result.risks.append("BODY_SUPPORT_DATA_INSUFFICIENT")
        return result

    bars = [_body_bar(row) for row in rows]
    atrs = _wilder_atr(rows, 14)
    tail_start = _tail_start_index(rows, phase)
    reference_start = max(0, tail_start - int(config["reference_window_days"]))
    pivots = _confirmed_pivots(rows, bars, atrs, reference_start, config)
    current_pivots = [pivot for pivot in pivots if pivot.index >= tail_start]

    anchor_pivots = pivots[-3:]
    floor_price = median([pivot.body_bottom for pivot in anchor_pivots]) if anchor_pivots else None
    latest_atr = atrs[-1] if atrs else 0.0
    if floor_price is not None:
        zone_width = max(
            floor_price * float(config["zone_min_width_pct"]),
            latest_atr * float(config["zone_atr_width"]),
        )
        result.floor_price = floor_price
        result.zone_low = floor_price - zone_width
        result.zone_high = floor_price + zone_width
        low_break_count = sum(1 for bar in bars[reference_start:] if bar["low"] < result.zone_low)
        body_break_count = sum(1 for bar in bars[reference_start:] if bar["bottom"] < result.zone_low)
        result.rejection_ratio = (
            (low_break_count - body_break_count) / low_break_count
            if low_break_count else 0.0
        )

    result.pivot_count = len(pivots)
    result.independent_touch_count = _independent_touch_count(rows, pivots, config)
    result.body_hold_pass = bool(current_pivots)
    if current_pivots:
        latest_pivot = current_pivots[-1]
        result.recovery_pass = latest_pivot.recovery_atr >= float(config["recovery_valid_atr"])
        result.recovery_atr = latest_pivot.recovery_atr
        result.low_rejection = any(p.low_rejection for p in current_pivots)
        result.volume_quality_pass = latest_pivot.volume_quality
    if len(pivots) >= 2:
        previous = pivots[-2].body_bottom
        latest = pivots[-1].body_bottom
        result.body_floor_migration = latest / previous - 1 if previous else None
        day_distance = max(pivots[-1].index - pivots[-2].index, 1)
        result.body_pivot_slope = (latest - previous) / day_distance
        result.cluster_width = (
            (max(p.body_bottom for p in pivots[-3:]) - min(p.body_bottom for p in pivots[-3:]))
            / median(p.body_bottom for p in pivots[-3:])
        )

    result.support_confluence = _support_confluence(result, support, latest_atr, config)
    path_scores: list[tuple[str, int]] = []
    if current_pivots:
        path_scores.append(("SINGLE_BODY_PIVOT", _single_score(current_pivots[-1], result, config)))
    if (
        current_pivots
        and len(pivots) >= int(config["flat_min_pivot_count"])
        and result.independent_touch_count >= int(config["flat_min_pivot_count"])
    ):
        width = result.cluster_width if result.cluster_width is not None else 1.0
        if width <= float(config["flat_valid_width"]):
            score = 7 + int(width <= float(config["flat_strong_width"])) + int(
                width <= float(config["flat_premium_width"])
            )
            path_scores.append(("FLAT_BODY_FLOOR", min(score, 10)))
        tolerance = float(config["rising_max_lower_tolerance_pct"])
        if pivots[-1].body_bottom >= pivots[-2].body_bottom * (1 - tolerance):
            score = 7 + int(pivots[-1].body_bottom > pivots[-2].body_bottom)
            path_scores.append(("RISING_BODY_FLOOR", score))

    failed_break = _recent_failed_break(rows, bars, result, tail_start)
    if failed_break:
        result.failed_breakout = True
        result.bear_follow_through_failure = True
        path_scores.append(("FAILED_BREAK_BODY_FLOOR", 8 + int(result.support_confluence)))

    if len(path_scores) >= 2:
        path_scores.append(("COMPOSITE_BODY_FLOOR", min(max(score for _, score in path_scores) + 1, 10)))

    if path_scores:
        result.support_type, result.score = max(path_scores, key=lambda item: item[1])
        result.passed = result.score >= 6
        result.status = "BODY_SUPPORT_STRONG" if result.score >= 8 else "BODY_SUPPORT_CONFIRMED"
        result.reasons.extend(_result_reasons(result))
    else:
        result.risks.append("NO_CURRENT_TAIL_BODY_SUPPORT_EVIDENCE")

    if result.zone_low is not None and bars[-1]["bottom"] < result.zone_low:
        consecutive_break = len(bars) >= 2 and bars[-2]["bottom"] < result.zone_low
        result.passed = False
        result.score = 0 if consecutive_break else min(result.score, 5)
        result.status = "BODY_SUPPORT_BROKEN" if consecutive_break else "BODY_SUPPORT_WEAKENED"
        result.risks.append(
            "CONSECUTIVE_BODY_BREAK_SUPPORT_ZONE"
            if consecutive_break else "LATEST_BODY_BROKE_SUPPORT_ZONE"
        )

    latest_pattern = _latest_bar_pattern(rows, bars, result, pivots, config)
    result.latest_bar_patterns = [latest_pattern]
    if latest_pattern.matched and result.score < 4 and result.status not in {"BODY_SUPPORT_BROKEN", "BODY_SUPPORT_WEAKENED"}:
        result.score = 5
        result.status = "BODY_SUPPORT_FORMING"
        result.reasons.extend(latest_pattern.reasons)
    return result


def _body_bar(row: dict) -> dict:
    open_ = float(row.get("open") or 0.0)
    close = float(row.get("close") or 0.0)
    return {
        "date": str(row.get("date") or ""),
        "open": open_,
        "close": close,
        "high": float(row.get("high") or max(open_, close)),
        "low": float(row.get("low") or min(open_, close)),
        "volume": float(row.get("volume") or 0.0),
        "bottom": min(open_, close),
        "top": max(open_, close),
    }


def _tail_start_index(rows: list[dict], phase: Strategy6Phase) -> int:
    if phase.valid and 0 <= phase.tail_start_index < len(rows):
        return phase.tail_start_index
    return max(0, len(rows) - 5)


def _wilder_atr(rows: list[dict], period: int) -> list[float]:
    true_ranges: list[float] = []
    for index, row in enumerate(rows):
        high = float(row.get("high") or 0.0)
        low = float(row.get("low") or 0.0)
        previous_close = float(rows[index - 1].get("close") or 0.0) if index else 0.0
        true_ranges.append(
            high - low if not index else max(high - low, abs(high - previous_close), abs(low - previous_close))
        )
    atrs: list[float] = []
    for index, value in enumerate(true_ranges):
        if index == 0:
            atrs.append(value)
        elif index < period:
            atrs.append(sum(true_ranges[: index + 1]) / (index + 1))
        else:
            atrs.append((atrs[-1] * (period - 1) + value) / period)
    return atrs


def _confirmed_pivots(rows, bars, atrs, start, config) -> list[_Pivot]:
    left = int(config["pivot_left_days"])
    confirm_days = int(config["confirm_days"])
    recovery_days = int(config["recovery_window_days"])
    pivots: list[_Pivot] = []
    final_index = len(rows) - confirm_days - 1
    for index in range(max(start, left), final_index + 1):
        bottom = bars[index]["bottom"]
        if not all(bottom <= bars[index - offset]["bottom"] for offset in range(1, left + 1)):
            continue
        if not all(bottom <= bars[index + offset]["bottom"] for offset in range(1, confirm_days + 1)):
            continue
        atr = max(atrs[index], 1e-9)
        hold_floor = min(
            bottom * (1 - float(config["body_hold_max_break_pct"])),
            bottom - atr * float(config["body_hold_max_break_atr"]),
        )
        confirm_slice = bars[index + 1 : index + confirm_days + 1]
        if min(bar["bottom"] for bar in confirm_slice) < hold_floor:
            continue
        recovery_slice = bars[index + 1 : min(len(bars), index + recovery_days + 1)]
        recovery_atr = (max(bar["close"] for bar in recovery_slice) - bottom) / atr
        if recovery_atr < float(config["recovery_valid_atr"]):
            continue
        bar_range = max(bars[index]["high"] - bars[index]["low"], 1e-9)
        lower_shadow = bars[index]["bottom"] - bars[index]["low"]
        prior_volumes = [bar["volume"] for bar in bars[max(0, index - 10) : index] if bar["volume"] > 0]
        pivots.append(_Pivot(
            index=index,
            body_bottom=bottom,
            low=bars[index]["low"],
            close=bars[index]["close"],
            atr=atr,
            recovery_atr=recovery_atr,
            low_rejection=lower_shadow / bar_range >= float(config["lower_shadow_ratio_min"]),
            volume_quality=bool(prior_volumes) and bars[index]["volume"] <= sum(prior_volumes) / len(prior_volumes),
        ))
    return pivots


def _single_score(pivot: _Pivot, result: Strategy6BodySupport, config: dict) -> int:
    score = 6
    score += int(pivot.recovery_atr >= float(config["recovery_premium_atr"]))
    score += int(pivot.low_rejection)
    score += int(result.support_confluence)
    score += int(pivot.volume_quality)
    return min(score, 10)


def _independent_touch_count(rows, pivots, config) -> int:
    if not pivots:
        return 0
    count = 1
    for previous, current in zip(pivots, pivots[1:]):
        interim = rows[previous.index + 1 : current.index]
        rebound = max((float(row.get("close") or 0.0) for row in interim), default=previous.body_bottom)
        required = max(
            previous.body_bottom * float(config["independent_rebound_pct"]),
            previous.atr * float(config["independent_rebound_atr"]),
        )
        if rebound - previous.body_bottom >= required:
            count += 1
    return count


def _support_confluence(result, support, atr, config) -> bool:
    if result.floor_price is None:
        return False
    prices = [
        support.key_support_price,
        support.tactical_support_price,
        support.pivot_price,
    ]
    tolerance = max(
        result.floor_price * float(config["support_confluence_pct"]),
        atr * float(config["support_confluence_atr"]),
    )
    return any(price and abs(result.floor_price - price) <= tolerance for price in prices)


def _recent_failed_break(rows, bars, result, tail_start) -> bool:
    if result.zone_low is None or result.floor_price is None:
        return False
    for index in range(tail_start, len(rows)):
        bar = bars[index]
        if bar["low"] < result.zone_low and bar["bottom"] >= result.zone_low:
            later = bars[index + 1 : min(len(bars), index + 3)]
            if later and all(item["bottom"] >= result.zone_low for item in later):
                return True
    return False


def _latest_bar_pattern(rows, bars, result, pivots, config) -> Strategy6LatestBarPattern:
    latest = bars[-1]
    pattern = Strategy6LatestBarPattern(
        code="VALID_BODY_LOW",
        name="有效实体低点",
        evaluation_date=latest["date"],
        body_bottom=latest["bottom"],
        body_top=latest["top"],
        body_direction=("BULLISH" if latest["close"] > latest["open"] else "BEARISH" if latest["close"] < latest["open"] else "FLAT"),
        floor_price=result.floor_price,
        zone_low=result.zone_low,
        zone_high=result.zone_high,
    )
    if result.floor_price:
        pattern.distance_to_floor_pct = latest["bottom"] / result.floor_price - 1
    if result.zone_low is not None and latest["low"] < result.zone_low <= latest["bottom"]:
        pattern.matched = True
        pattern.signal_type = "FAILED_BREAK_RECLAIM"
        pattern.reasons.append("LATEST_LOW_BREAK_RECLAIMED_BY_BODY")
    elif result.zone_low is not None and result.zone_high is not None and latest["low"] <= result.zone_high and latest["bottom"] >= result.zone_low:
        pattern.matched = True
        pattern.signal_type = "BODY_FLOOR_HOLD"
        pattern.reasons.append("LATEST_BODY_HELD_SUPPORT_ZONE")
    elif len(bars) >= 3 and latest["bottom"] <= min(bars[-2]["bottom"], bars[-3]["bottom"]):
        bar_range = max(latest["high"] - latest["low"], 1e-9)
        lower_shadow_ratio = (latest["bottom"] - latest["low"]) / bar_range
        if latest["close"] >= latest["open"] or lower_shadow_ratio >= float(config["lower_shadow_ratio_min"]):
            pattern.matched = True
            pattern.signal_type = "POTENTIAL_BODY_PIVOT"
            pattern.reasons.append("LATEST_BODY_POTENTIAL_PIVOT")
    if pattern.matched:
        pattern.status = "CONFIRMING"
        pattern.risks.append("REQUIRES_TWO_COMPLETED_BARS_TO_CONFIRM_PIVOT")
    else:
        pattern.reasons.append("LATEST_BAR_NO_VALID_BODY_LOW")
    return pattern


def _result_reasons(result: Strategy6BodySupport) -> list[str]:
    reasons = [result.support_type]
    if result.body_hold_pass:
        reasons.append("BODY_HOLD_CONFIRMED")
    if result.recovery_pass:
        reasons.append("BODY_RECOVERY_CONFIRMED")
    if result.low_rejection:
        reasons.append("LOW_PRICE_REJECTION")
    if result.support_confluence:
        reasons.append("BODY_SUPPORT_CONFLUENCE")
    return reasons
