"""Price-only detector for the slow rounded base pattern family.

Every candidate window ends on the latest valid trading day.  The detector
scores structural behaviour instead of comparing against a fixed reference
path, drawdown or duration.
"""
from __future__ import annotations

import math
from statistics import median


MODEL_VERSION = "SLOW_ROUNDED_BASE_V2"
MIN_WINDOW_DAYS = 10
MAX_WINDOW_DAYS = 30
SEARCH_LOOKBACK_DAYS = 50


def evaluate_slow_rounded_base(
    rows: list[dict],
    *,
    min_window_days: int = MIN_WINDOW_DAYS,
    max_window_days: int = MAX_WINDOW_DAYS,
    search_lookback_days: int = SEARCH_LOOKBACK_DAYS,
) -> dict:
    """Return the best current slow-rounded-base window and diagnostics."""
    input_rows = rows or []
    valid_rows = _valid_rows(input_rows)
    if input_rows and (
        not valid_rows
        or valid_rows[-1].get("date") != input_rows[-1].get("date")
    ):
        return _unavailable(input_rows[-1].get("date", ""), "DATA_INVALID", "LATEST_BAR_INVALID")
    valid_rows = valid_rows[-max(search_lookback_days, max_window_days):]
    if len(valid_rows) < min_window_days:
        return _insufficient(valid_rows)

    atr14 = _atr(valid_rows, 14)
    candidates = [
        _score_window(valid_rows[-window_days:], atr14)
        for window_days in range(
            min_window_days,
            min(max_window_days, len(valid_rows)) + 1,
        )
    ]
    return max(
        candidates,
        key=lambda item: (
            item["score"],
            sum(item["invariants"].values()),
            item["features"]["bottom_dwell_ratio"],
            item["window_days"],
        ),
    )


def _score_window(rows: list[dict], atr14: float | None) -> dict:
    closes = [row["close"] for row in rows]
    highs = [row["high"] for row in rows]
    lows = [row["low"] for row in rows]
    volumes = [row.get("volume", 0.0) for row in rows]
    count = len(rows)
    smooth = _ema(closes, 3)

    first_end = max(3, math.ceil(count * 0.30))
    middle_end = max(first_end + 3, math.ceil(count * 0.65))
    early_slope = _log_slope(smooth[:first_end])
    middle_slope = _log_slope(smooth[first_end:middle_end])
    late_slope = _log_slope(smooth[middle_end:])

    # The window must begin with a real pullback.  Restricting the anchor to
    # the early section prevents a completed V-rebound from inventing a new
    # tiny pullback around the already elevated right side.
    peak_search_end = max(3, math.ceil(count * 0.30))
    peak_idx = max(range(peak_search_end), key=lambda index: highs[index])
    low_idx = min(range(count), key=lambda index: closes[index])
    intraday_low_idx = min(range(count), key=lambda index: lows[index])
    peak_price = highs[peak_idx]
    trough_price = min(lows[peak_idx:])
    pullback_depth = max(0.0, 1.0 - trough_price / peak_price)
    close_pullback_depth = (
        max(0.0, 1.0 - closes[low_idx] / closes[peak_idx])
        if peak_idx < low_idx
        else 0.0
    )

    returns = [closes[index] / closes[index - 1] - 1.0 for index in range(1, count)]
    down_returns = [-value for value in returns if value < 0]
    median_down_pct = median(down_returns) if down_returns else 0.0
    rolling_slopes = [
        _log_slope(smooth[index - 4:index + 1])
        for index in range(4, count)
    ]
    slope_improvement_ratio = _improvement_ratio(rolling_slopes)

    robust_range = max(0.0, _quantile(closes, 0.80) - _quantile(closes, 0.20))
    bottom_tolerance = max(robust_range * 0.35, (atr14 or 0.0) * 0.75)
    if robust_range > 0:
        bottom_tolerance = min(bottom_tolerance, robust_range * 0.70)
    # Anchor the zone to the lower close decile rather than one exceptional
    # wick/close.  A rounded base is an area occupied by several closes.
    bottom_zone_top = _quantile(closes[peak_idx:], 0.10) + bottom_tolerance
    bottom_indexes = [
        index for index in range(peak_idx, count)
        if closes[index] <= bottom_zone_top
    ]
    bottom_days = len(bottom_indexes)
    bottom_dwell_ratio = bottom_days / count
    bottom_span_days = bottom_indexes[-1] - bottom_indexes[0] + 1 if bottom_indexes else 0
    bars_after_low = count - 1 - low_idx
    after_low_ratio = bars_after_low / count

    rolling_ranges = _rolling_ranges(highs, lows, closes, 5)
    range_split = max(1, len(rolling_ranges) // 2)
    early_ranges = rolling_ranges[:range_split]
    late_ranges = rolling_ranges[range_split:]
    early_range = median(early_ranges) if early_ranges else 0.0
    late_range = median(late_ranges) if late_ranges else early_range
    range_contraction_ratio = late_range / early_range if early_range > 0 else 1.0

    late_closes = closes[count // 2:]
    late_cluster80 = (
        (_quantile(late_closes, 0.90) - _quantile(late_closes, 0.10))
        / median(late_closes)
        if late_closes and median(late_closes) > 0
        else 1.0
    )
    overlaps = _adjacent_overlaps(highs, lows)
    overlap_split = max(1, len(overlaps) // 2)
    early_overlap = sum(overlaps[:overlap_split]) / overlap_split
    late_overlap_values = overlaps[overlap_split:]
    late_overlap = (
        sum(late_overlap_values) / len(late_overlap_values)
        if late_overlap_values else early_overlap
    )

    rebound_end = min(count, low_idx + 4)
    rebound_3 = max(closes[low_idx:rebound_end]) / closes[low_idx] - 1.0
    extension_from_low = closes[-1] / closes[low_idx] - 1.0
    volume_dry_ratio = _late_to_early_ratio(volumes)

    prior_pullback = (
        peak_idx < low_idx
        and pullback_depth >= 0.025
        and close_pullback_depth >= 0.015
        and peak_idx <= math.floor(count * 0.45)
    )
    decelerating = (
        early_slope < -0.0005
        and late_slope > early_slope + 0.0007
        and (slope_improvement_ratio >= 0.35 or late_slope >= -0.0015)
    )
    bottom_width = bottom_days >= 3 and bottom_dwell_ratio >= 0.20 and bottom_span_days >= 3
    stabilizing = range_contraction_ratio <= 1.05 or late_cluster80 <= 0.055
    no_v_reversal = (
        rebound_3 <= 0.10
        and extension_from_low <= 0.12
        and bars_after_low >= 2
        and intraday_low_idx < count - 1
    )

    component_scores = {
        "slow_pullback": round(
            _descending_score(median_down_pct, [(0.010, 10), (0.015, 8.5), (0.022, 6), (0.030, 2), (0.040, 0)])
            + _pullback_depth_score(pullback_depth),
            2,
        ),
        "deceleration": round(
            _deceleration_score(early_slope, late_slope)
            + _ascending_score(slope_improvement_ratio, [(0.30, 0), (0.45, 5), (0.55, 7.5), (0.65, 10)]),
            2,
        ),
        "bottom_width": round(
            _ascending_score(bottom_dwell_ratio, [(0.15, 0), (0.25, 7), (0.35, 10), (0.45, 12)])
            + _ascending_score(bottom_days, [(1, 0), (3, 3), (5, 6), (8, 8)]),
            2,
        ),
        "after_low": round(
            _ascending_score(bars_after_low, [(1, 0), (3, 4), (5, 7), (7, 8)])
            + _ascending_score(after_low_ratio, [(0.08, 0), (0.20, 1), (0.32, 2)]),
            2,
        ),
        "volatility_contraction": round(
            max(
                _descending_score(range_contraction_ratio, [(0.60, 12), (0.75, 10), (0.90, 7), (1.00, 4), (1.20, 0)]),
                # An already low late range still carries some quality even
                # when the early half was unusually quiet.  This is a broad
                # absolute fallback, not a reference-sample threshold.
                _descending_score(late_range, [(0.045, 6), (0.060, 5), (0.080, 4), (0.120, 0)]),
            ),
            2,
        ),
        "close_clustering": round(
            _descending_score(late_cluster80, [(0.035, 8), (0.050, 6.5), (0.080, 3), (0.120, 0)]),
            2,
        ),
        "overlap_improvement": round(
            min(5.0, max(0.0, late_overlap * 5.0 + max(0.0, late_overlap - early_overlap) * 3.0)),
            2,
        ),
        "no_v_reversal": round(_no_v_score(rebound_3, extension_from_low, bars_after_low), 2),
    }
    raw_score = sum(component_scores.values())
    invariants = {
        "prior_pullback": prior_pullback,
        "deceleration": decelerating,
        "bottom_width": bottom_width,
        "stabilization": stabilizing,
        "no_v_reversal": no_v_reversal,
    }
    score_cap = 100.0
    if not prior_pullback:
        score_cap = min(score_cap, 64.0)
    if not all((decelerating, bottom_width, stabilizing, no_v_reversal)):
        score_cap = min(score_cap, 71.0)
    score = round(min(100.0, raw_score, score_cap), 2)
    matched = score >= 72 and all(invariants.values())
    strong_matched = matched and score >= 80
    status = "STRONG_MATCHED" if strong_matched else "MATCHED" if matched else "FORMING" if score >= 65 else "NOT_MATCHED"

    reasons = []
    warnings = []
    if component_scores["slow_pullback"] >= 10:
        reasons.append("PULLBACK_PACE_GENTLE")
    if decelerating:
        reasons.append("DECLINE_DECELERATING")
    if bottom_width:
        reasons.append("BOTTOM_AREA_HAS_TIME_WIDTH")
    if stabilizing:
        reasons.append("LATE_PATH_STABILIZING")
    if no_v_reversal:
        reasons.append("NO_V_REVERSAL")
    if not prior_pullback:
        warnings.append("PRIOR_PULLBACK_MISSING")
    if not decelerating:
        warnings.append("DECLINE_NOT_DECELERATING")
    if not bottom_width:
        warnings.append("BOTTOM_AREA_TOO_NARROW")
    if not stabilizing:
        warnings.append("LATE_PATH_NOT_STABLE")
    if not no_v_reversal:
        warnings.append("V_REVERSAL_OR_ALREADY_EXTENDED")

    return {
        "code": "SLOW_ROUNDED_BASE",
        "name": "缓跌圆底",
        "matched": matched,
        "strong_matched": strong_matched,
        "status": status,
        "score": score,
        "grade": _grade(score),
        "start_date": rows[0].get("date", ""),
        "end_date": rows[-1].get("date", ""),
        "window_days": count,
        "features": {
            "pullback_depth": round(pullback_depth, 6),
            "close_pullback_depth": round(close_pullback_depth, 6),
            "median_down_pct": round(median_down_pct, 6),
            "early_slope": round(early_slope, 6),
            "middle_slope": round(middle_slope, 6),
            "late_slope": round(late_slope, 6),
            "slope_improvement_ratio": round(slope_improvement_ratio, 6),
            "low_position": round(low_idx / max(1, count - 1), 6),
            "bottom_days": bottom_days,
            "bottom_span_days": bottom_span_days,
            "bottom_dwell_ratio": round(bottom_dwell_ratio, 6),
            "bars_after_low": bars_after_low,
            "after_low_ratio": round(after_low_ratio, 6),
            "early_range": round(early_range, 6),
            "late_range": round(late_range, 6),
            "range_contraction_ratio": round(range_contraction_ratio, 6),
            "late_cluster80": round(late_cluster80, 6),
            "early_overlap": round(early_overlap, 6),
            "late_overlap": round(late_overlap, 6),
            "rebound_3": round(rebound_3, 6),
            "extension_from_low": round(extension_from_low, 6),
            "volume_dry_ratio": round(volume_dry_ratio, 6) if volume_dry_ratio is not None else None,
        },
        "component_scores": component_scores,
        "invariants": invariants,
        "reasons": reasons,
        "warnings": warnings,
        "model_version": MODEL_VERSION,
    }


def _valid_rows(rows: list[dict]) -> list[dict]:
    result = []
    for row in rows or []:
        try:
            open_price = float(row.get("open"))
            high = float(row.get("high"))
            low = float(row.get("low"))
            close = float(row.get("close"))
            volume = float(row.get("volume") or 0.0)
        except (TypeError, ValueError):
            continue
        if not all(math.isfinite(value) and value > 0 for value in (open_price, high, low, close)):
            continue
        if high < max(open_price, close) or low > min(open_price, close) or high < low:
            continue
        result.append({**row, "open": open_price, "high": high, "low": low, "close": close, "volume": max(0.0, volume)})
    return result


def _insufficient(rows: list[dict]) -> dict:
    return {
        "code": "SLOW_ROUNDED_BASE", "name": "缓跌圆底", "matched": False,
        "strong_matched": False, "status": "DATA_INSUFFICIENT", "score": 0.0,
        "grade": "UNQUALIFIED", "start_date": rows[0].get("date", "") if rows else "",
        "end_date": rows[-1].get("date", "") if rows else "", "window_days": len(rows),
        "features": {}, "component_scores": {},
        "invariants": {"prior_pullback": False, "deceleration": False, "bottom_width": False, "stabilization": False, "no_v_reversal": False},
        "reasons": [], "warnings": ["PATTERN_DATA_INSUFFICIENT"], "model_version": MODEL_VERSION,
    }


def _unavailable(end_date: str, status: str, warning: str) -> dict:
    result = _insufficient([])
    result.update({"status": status, "end_date": end_date, "warnings": [warning]})
    return result


def _ema(values: list[float], span: int) -> list[float]:
    alpha = 2.0 / (span + 1.0)
    result = [values[0]]
    for value in values[1:]:
        result.append(alpha * value + (1.0 - alpha) * result[-1])
    return result


def _log_slope(values: list[float]) -> float:
    if len(values) < 2 or any(value <= 0 for value in values):
        return 0.0
    logs = [math.log(value) for value in values]
    mean_x = (len(values) - 1) / 2.0
    mean_y = sum(logs) / len(logs)
    denominator = sum((index - mean_x) ** 2 for index in range(len(values)))
    if denominator == 0:
        return 0.0
    return sum((index - mean_x) * (value - mean_y) for index, value in enumerate(logs)) / denominator


def _improvement_ratio(slopes: list[float]) -> float:
    if len(slopes) < 2:
        return 0.0
    return sum(slopes[index] > slopes[index - 1] for index in range(1, len(slopes))) / (len(slopes) - 1)


def _rolling_ranges(highs: list[float], lows: list[float], closes: list[float], window: int) -> list[float]:
    return [
        (max(highs[index - window + 1:index + 1]) - min(lows[index - window + 1:index + 1]))
        / median(closes[index - window + 1:index + 1])
        for index in range(window - 1, len(closes))
    ]


def _adjacent_overlaps(highs: list[float], lows: list[float]) -> list[float]:
    result = []
    for index in range(1, len(highs)):
        intersection = max(0.0, min(highs[index - 1], highs[index]) - max(lows[index - 1], lows[index]))
        union = max(highs[index - 1], highs[index]) - min(lows[index - 1], lows[index])
        result.append(intersection / union if union > 0 else 0.0)
    return result


def _atr(rows: list[dict], period: int) -> float | None:
    if len(rows) < period + 1:
        return None
    true_ranges = []
    for index in range(1, len(rows)):
        previous_close = rows[index - 1]["close"]
        true_ranges.append(max(
            rows[index]["high"] - rows[index]["low"],
            abs(rows[index]["high"] - previous_close),
            abs(rows[index]["low"] - previous_close),
        ))
    value = sum(true_ranges[:period]) / period
    for true_range in true_ranges[period:]:
        value = (value * (period - 1) + true_range) / period
    return value


def _quantile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _interpolate(value: float, points: list[tuple[float, float]]) -> float:
    if value <= points[0][0]:
        return points[0][1]
    for (left_x, left_y), (right_x, right_y) in zip(points, points[1:]):
        if value <= right_x:
            ratio = (value - left_x) / (right_x - left_x)
            return left_y + (right_y - left_y) * ratio
    return points[-1][1]


def _ascending_score(value: float, points: list[tuple[float, float]]) -> float:
    return _interpolate(value, points)


def _descending_score(value: float, points: list[tuple[float, float]]) -> float:
    return _interpolate(value, points)


def _pullback_depth_score(depth: float) -> float:
    if depth < 0.03:
        return _interpolate(depth, [(0.0, 0), (0.03, 2.5)])
    if depth <= 0.15:
        return _interpolate(depth, [(0.03, 2.5), (0.05, 5), (0.15, 5)])
    return _interpolate(depth, [(0.15, 5), (0.20, 2.5), (0.25, 0)])


def _deceleration_score(early_slope: float, late_slope: float) -> float:
    if early_slope >= -0.0001:
        return 0.0
    improvement = (late_slope - early_slope) / abs(early_slope)
    return _interpolate(improvement, [(0.0, 0), (0.30, 6), (0.60, 11), (1.0, 15)])


def _no_v_score(rebound_3: float, extension: float, bars_after_low: int) -> float:
    if bars_after_low < 2 or rebound_3 > 0.10 or extension > 0.12:
        return 0.0
    return min(
        _descending_score(rebound_3, [(0.04, 5), (0.07, 4), (0.10, 2)]),
        _descending_score(extension, [(0.06, 5), (0.10, 3), (0.12, 2)]),
    )


def _late_to_early_ratio(values: list[float]) -> float | None:
    positive = [value for value in values if value > 0]
    if len(positive) != len(values) or len(values) < 4:
        return None
    split = len(values) // 2
    early = median(values[:split])
    late = median(values[split:])
    return late / early if early > 0 else None


def _grade(score: float) -> str:
    if score >= 88:
        return "S"
    if score >= 80:
        return "A"
    if score >= 72:
        return "B"
    if score >= 65:
        return "C"
    return "UNQUALIFIED"
