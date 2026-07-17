"""Cup-and-handle, VCP and platform detection for Strategy6."""
from __future__ import annotations

from strategy6.models import Strategy6Pattern, Strategy6Phase
from strategy6.vcp_rounds import detect_vcp_rounds


def detect_pattern(rows: list[dict], phase: Strategy6Phase, config: dict) -> Strategy6Pattern:
    if not phase.valid:
        return Strategy6Pattern(reasons=[phase.status])
    # The signal bar is evaluated against a structure that already existed;
    # including it would move the pivot and make breakouts self-referential.
    consolidation = rows[phase.consolidation_start_index:phase.tail_start_index]
    if len(consolidation) < int(config["consolidation_min_days"]):
        return Strategy6Pattern(reasons=["PATTERN_DATA_INSUFFICIENT"])

    signal_price = float(rows[phase.signal_index]["close"])
    cup = _detect_cup_handle(consolidation, config)
    if cup.pattern_type != "UNKNOWN":
        return cup
    vcp = _detect_vcp(consolidation, signal_price, config)
    if vcp.pattern_type != "UNKNOWN":
        return vcp
    platform = _detect_platform(consolidation, signal_price, config)
    if platform.pattern_type != "UNKNOWN":
        return platform
    return Strategy6Pattern(
        pattern_start_date=consolidation[0]["date"],
        pattern_end_date=consolidation[-1]["date"],
        reasons=["PATTERN_NOT_RECOGNIZED"],
    )


def _detect_vcp(rows: list[dict], signal_price: float, config: dict) -> Strategy6Pattern:
    if len(rows) < 10:
        return Strategy6Pattern()
    detection = detect_vcp_rounds(rows, config)
    if not detection.confirmed:
        return Strategy6Pattern()
    rounds = detection.completed_rounds
    last = rounds[-1]
    pivot = last.recovery_peak_close
    low = last.low_close
    proximity = float(config["pattern_pivot_proximity_pct"])
    if pivot <= 0 or signal_price < pivot * (1 - proximity):
        return Strategy6Pattern()
    return Strategy6Pattern(
        pattern_type="VCP",
        pattern_score=min(20, 16 + len(rounds)),
        pattern_start_date=str(rounds[0].peak_date or ""),
        pattern_end_date=str(last.recovery_peak_date or ""),
        pivot_source="VCP_LAST_RECOVERY_PEAK",
        pivot_price=round(pivot, 4),
        pattern_low=round(low, 4),
        pattern_height=round(max(0.0, pivot - low), 4),
        depth_pct=round(last.amplitude, 6),
        contraction_count=len(rounds),
        reasons=["VCP_COMPLETE_ROUNDS", "VCP_RANGE_CONTRACTING", "VCP_VOLUME_CONTRACTING"],
    )


def _swing_contractions(rows: list[dict]) -> list[dict]:
    closes = [float(row["close"]) for row in rows]
    peak_indexes: list[int] = []
    for idx in range(len(rows) - 1):
        current = closes[idx]
        previous = closes[idx - 1] if idx > 0 else float("-inf")
        following = closes[idx + 1]
        if current >= previous and current > following:
            peak_indexes.append(idx)

    contractions: list[dict] = []
    for position, peak_index in enumerate(peak_indexes):
        boundary = peak_indexes[position + 1] if position + 1 < len(peak_indexes) else len(rows)
        if peak_index + 1 >= boundary:
            continue
        low_index = min(range(peak_index + 1, boundary), key=lambda idx: closes[idx])
        peak_close = closes[peak_index]
        low_close = closes[low_index]
        amplitude = (peak_close - low_close) / peak_close if peak_close > 0 else 0.0
        if amplitude <= 0:
            continue
        segment = rows[peak_index:low_index + 1]
        contractions.append({
            "peak_index": peak_index,
            "low_index": low_index,
            "peak_close": peak_close,
            "low_close": low_close,
            "amplitude": amplitude,
            "avg_volume": _mean(row["volume"] for row in segment),
        })
    return contractions


def _best_vcp_chain(contractions: list[dict], config: dict) -> list[dict]:
    range_ratio = float(config["vcp_contraction_range_ratio"])
    volume_ratio = float(config["vcp_contraction_volume_ratio"])
    minimum_first = float(config["vcp_min_first_range"])
    best: list[dict] = []
    for index, first in enumerate(contractions):
        if first["amplitude"] < minimum_first or first["avg_volume"] <= 0:
            continue
        chain = [first]
        for candidate in contractions[index + 1:]:
            previous = chain[-1]
            if (
                candidate["peak_index"] > previous["low_index"]
                and candidate["amplitude"] < previous["amplitude"] * range_ratio
                and candidate["avg_volume"] < previous["avg_volume"] * volume_ratio
                and candidate["low_close"] >= previous["low_close"] * 0.97
            ):
                chain.append(candidate)
            else:
                break
        if len(chain) >= 2 and (
            len(chain) > len(best)
            or (len(chain) == len(best) and chain[-1]["low_index"] > best[-1]["low_index"])
        ):
            best = chain
    return best


def _detect_cup_handle(rows: list[dict], config: dict) -> Strategy6Pattern:
    if len(rows) < 12:
        return Strategy6Pattern()
    handle_len = max(3, min(5, len(rows) // 4))
    body = rows[:-handle_len]
    handle = rows[-handle_len:]
    left_end = max(2, len(body) // 3)
    left = body[:left_end]
    left_peak_index = max(range(len(left)), key=lambda idx: body[idx]["close"])
    left_high = body[left_peak_index]["close"]
    if left_peak_index + 1 >= len(body):
        return Strategy6Pattern()
    bottom_index = min(
        range(left_peak_index + 1, len(body)),
        key=lambda idx: body[idx]["close"],
    )
    bottom = body[bottom_index]["close"]
    right = body[bottom_index + 1:]
    if not right or left_high <= 0:
        return Strategy6Pattern()
    depth = (left_high - bottom) / left_high
    right_high = max(row["close"] for row in right)
    handle_high = max(row["close"] for row in handle)
    handle_low = min(row["close"] for row in handle)
    handle_depth = (handle_high - handle_low) / handle_high if handle_high > 0 else 1.0
    right_volume = _mean(row["volume"] for row in right[-5:])
    handle_volume = _mean(row["volume"] for row in handle)
    if not (
        float(config["cup_depth_min"]) <= depth <= float(config["cup_depth_max"])
        and 0.90 <= right_high / left_high <= 1.00
        and handle_depth <= depth / 3
        and handle_volume < right_volume
    ):
        return Strategy6Pattern()
    pivot = handle_high
    return Strategy6Pattern(
        pattern_type="CUP_HANDLE",
        pattern_score=19,
        pattern_start_date=rows[0]["date"],
        pattern_end_date=rows[-1]["date"],
        pivot_source="CUP_HANDLE_PIVOT",
        pivot_price=round(pivot, 4),
        pattern_low=round(handle_low, 4),
        pattern_height=round(max(0.0, pivot - handle_low), 4),
        depth_pct=round(depth, 6),
        reasons=["CUP_DEPTH_VALID", "RIGHT_SIDE_RECOVERED", "HANDLE_VOLUME_DRY"],
    )


def _detect_platform(rows: list[dict], signal_price: float, config: dict) -> Strategy6Pattern:
    if len(rows) < 5:
        return Strategy6Pattern()
    range_pct = _range_pct(rows)
    split = len(rows) // 2
    first_low = min(row["low"] for row in rows[:split])
    second_low = min(row["low"] for row in rows[split:])
    first_volume = _mean(row["volume"] for row in rows[:split])
    second_volume = _mean(row["volume"] for row in rows[split:])
    if not (
        range_pct <= float(config["platform_max_range"])
        and second_low >= first_low * 0.98
        and second_volume < first_volume
    ):
        return Strategy6Pattern()
    pivot = max(row["close"] for row in rows)
    low = min(row["close"] for row in rows)
    proximity = float(config["pattern_pivot_proximity_pct"])
    near_pivot = pivot > 0 and signal_price >= pivot * (1 - proximity)
    near_support = low > 0 and abs(signal_price / low - 1) <= proximity
    if not (near_pivot or near_support):
        return Strategy6Pattern()
    return Strategy6Pattern(
        pattern_type="PLATFORM",
        pattern_score=15,
        pattern_start_date=rows[0]["date"],
        pattern_end_date=rows[-1]["date"],
        pivot_source="PLATFORM_TOP",
        pivot_price=round(pivot, 4),
        pattern_low=round(low, 4),
        pattern_height=round(max(0.0, pivot - low), 4),
        depth_pct=round((pivot - low) / pivot, 6) if pivot > 0 else 0.0,
        reasons=["PLATFORM_RANGE_TIGHT", "PLATFORM_LOW_NOT_FALLING", "PLATFORM_VOLUME_DRY"],
    )


def _range_pct(rows: list[dict]) -> float:
    high = max((row["high"] for row in rows), default=0.0)
    low = min((row["low"] for row in rows), default=0.0)
    return (high - low) / high if high > 0 else 0.0


def _mean(values) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0
