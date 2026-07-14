"""Strategy6 stable-box tail path and compact K-line quality checks."""
from __future__ import annotations

from statistics import mean, median

from strategy6.brooks.metrics import calculate_kline_overlap_ratio as _shared_overlap_ratio
from strategy6.brooks.models import BrooksTailResult
from strategy6.indicators import _atr
from strategy6.models import (
    Strategy6BoxTail,
    Strategy6CompactKline,
    Strategy6DryTail,
    Strategy6Phase,
    Strategy6Support,
    Strategy6TailPaths,
)


def combine_tail_paths(
    original: Strategy6DryTail,
    box: Strategy6BoxTail,
    brooks: BrooksTailResult | None = None,
) -> Strategy6TailPaths:
    brooks = brooks or BrooksTailResult.disabled()
    original_pass = bool(original.dry_tail_pass)
    box_pass = bool(box.passed)
    if original_pass and box_pass:
        path = "BOTH"
    elif original_pass:
        path = "ORIGINAL"
    elif box_pass:
        path = "BOX"
    else:
        path = "NONE"
    brooks_pass = bool(brooks.passed)
    paths = [
        name for name, passed in (
            ("ORIGINAL", original_pass),
            ("BOX", box_pass),
            ("BROOKS", brooks_pass),
        ) if passed
    ]
    scores = {
        "ORIGINAL": int(original.dry_stable_score),
        "BOX": int(box.score),
        "BROOKS": int(brooks.score),
    }
    if paths:
        priority = {"ORIGINAL": 0, "BOX": 1, "BROOKS": 2}
        primary = max(paths, key=lambda name: (scores[name], priority[name]))
    else:
        primary = "NONE"
    score = 0
    if original_pass:
        score += 10
    if box_pass:
        score += 3
    if brooks_pass and bool(getattr(brooks.trade_trigger, "ready", False)):
        score += 2
    if len(paths) >= 2:
        score += 2
    score = min(15, score)
    summary = paths[0] if len(paths) == 1 else "MULTI" if paths else "NONE"
    return Strategy6TailPaths(
        original_pass=original_pass,
        original_score=int(original.dry_stable_score),
        box_pass=box_pass,
        box_score=int(box.score),
        brooks_pass=brooks_pass,
        brooks_score=int(brooks.score),
        passed=bool(paths),
        path=path,
        paths=paths,
        summary=summary,
        primary=primary,
        passed_path_count=len(paths),
        multi_path_confirmed=len(paths) >= 2,
        score=score,
    )


def evaluate_box_tail(
    rows: list[dict],
    phase: Strategy6Phase,
    support: Strategy6Support,
    original_tail: Strategy6DryTail,
    *,
    has_volume_selloff: bool,
    config: dict,
) -> Strategy6BoxTail:
    if not bool(config.get("enabled", True)):
        return Strategy6BoxTail(enabled=False)
    if not phase.valid or phase.signal_index < 0 or not rows:
        return Strategy6BoxTail(enabled=True, risk_tags=[phase.status or "BOX_PHASE_INVALID"])
    if "TAIL_VOLUME_BASE_INSUFFICIENT" in original_tail.rejects:
        return Strategy6BoxTail(
            enabled=True,
            risk_tags=["BOX_TAIL_VOLUME_BASE_INSUFFICIENT"],
        )

    first_allowed = max(phase.start_index + 1, phase.consolidation_start_index)
    signal_index = min(phase.signal_index, len(rows) - 1)
    results: list[Strategy6BoxTail] = []
    for days in range(int(config["min_box_days"]), int(config["max_box_days"]) + 1):
        start_index = signal_index - days + 1
        if start_index < first_allowed or start_index <= phase.start_index:
            continue
        box_data = rows[start_index:signal_index + 1]
        if len(box_data) != days or len(box_data) < 3:
            continue
        result = _evaluate_box_window(
            rows[:signal_index + 1],
            box_data,
            support,
            original_tail,
            has_volume_selloff=has_volume_selloff,
            config=config,
        )
        results.append(result)

    if not results:
        return Strategy6BoxTail(enabled=True, risk_tags=["NO_ELIGIBLE_BOX_WINDOW"])

    passing = [result for result in results if result.passed]
    selection_pool = passing or results
    selected = max(selection_pool, key=lambda result: (
        result.quality_score,
        result.days,
        -(result.box_width if result.box_width is not None else float("inf")),
        -(result.volume_contraction_ratio if result.volume_contraction_ratio is not None else float("inf")),
    ))
    selected.selection_reason = (
        "highest_box_quality_score_then_days_width_volume_contraction"
    )
    return selected


def _evaluate_box_window(
    all_rows: list[dict],
    box_data: list[dict],
    support: Strategy6Support,
    original_tail: Strategy6DryTail,
    *,
    has_volume_selloff: bool,
    config: dict,
) -> Strategy6BoxTail:
    result = Strategy6BoxTail(
        enabled=True,
        start_date=str(box_data[0].get("date") or ""),
        end_date=str(box_data[-1].get("date") or ""),
        days=len(box_data),
    )
    # The last two complete sessions confirm a break/current position. Keeping
    # them out of the structural boundary avoids a new low redefining box_low.
    structure = box_data[:-2]
    if not structure:
        result.risk_tags.append("BOX_STRUCTURE_DATA_INSUFFICIENT")
        return result
    closes = [float(row["close"]) for row in structure]
    result.box_high = round(max(closes), 4)
    result.box_low = round(min(closes), 4)
    if result.box_low <= 0 or result.box_high <= result.box_low:
        result.risk_tags.append("BOX_BOUNDARY_INVALID")
        return result

    result.box_width = round((result.box_high - result.box_low) / result.box_low, 6)
    result.low_test_count = count_independent_box_low_tests(structure, result.box_low, config)
    result.high_test_count = count_independent_box_high_tests(structure, result.box_high, config)

    split = len(structure) // 2
    first_half = structure[:split]
    second_half = structure[split:]
    if not first_half or not second_half:
        result.risk_tags.append("BOX_HALF_DATA_INSUFFICIENT")
        return result
    result.first_half_volume = round(mean(float(row["volume"]) for row in first_half), 4)
    result.second_half_volume = round(mean(float(row["volume"]) for row in second_half), 4)
    if result.first_half_volume <= 0:
        result.risk_tags.append("BOX_FIRST_HALF_VOLUME_INVALID")
        return result
    result.volume_contraction_ratio = round(result.second_half_volume / result.first_half_volume, 6)
    result.first_half_median_close = round(median(float(row["close"]) for row in first_half), 4)
    result.second_half_median_close = round(median(float(row["close"]) for row in second_half), 4)
    if result.first_half_median_close <= 0:
        result.risk_tags.append("BOX_FIRST_HALF_CENTER_INVALID")
        return result
    result.center_shift = round(
        result.second_half_median_close / result.first_half_median_close - 1,
        6,
    )

    current_close = float(box_data[-1]["close"])
    result.box_position_raw = round(
        (current_close - result.box_low) / (result.box_high - result.box_low),
        6,
    )
    result.box_position = round(min(1.0, max(0.0, result.box_position_raw)), 6)
    result.break_reason = _box_break_reason(
        box_data,
        result.box_low,
        support,
        has_volume_selloff=has_volume_selloff,
        config=config,
    )

    atr5 = _atr(all_rows, 5)
    atr20 = _atr(all_rows, 20)
    result.compact_kline = evaluate_compact_kline(
        box_data,
        atr5=atr5,
        atr20=atr20,
        tail_volume_ratio=original_tail.tail_volume_ratio,
        premium_tail_volume_ratio_max=config["premium_tail_volume_ratio_max"],
        has_volume_selloff=has_volume_selloff,
        config=config["compact_kline"],
    )
    support_floor = max(
        float(support.key_support_price or 0),
        float(support.support_zone_low or 0),
    )
    support_valid = support_floor <= 0 or current_close >= support_floor
    current_in_range = (
        current_close >= result.box_low * (1 - config["current_close_low_tolerance"])
        and current_close <= result.box_high * (1 + config["current_close_high_tolerance"])
    )
    conditions = {
        "width": result.box_width <= config["normal_box_width_max"],
        "low_tests": result.low_test_count >= config["min_box_low_test_count"],
        "center": result.center_shift >= config["min_center_shift"],
        "volume": result.volume_contraction_ratio <= config["max_volume_contraction_ratio"],
        "current_range": current_in_range,
        "tail_volume": original_tail.tail_volume_ratio <= config["tail_volume_ratio_max"],
        "selloff": not has_volume_selloff,
        "support": support_valid,
        "break": not result.break_reason,
    }
    result.passed = all(conditions.values())
    result.score = _calculate_box_score(
        result,
        tail_volume_ratio=original_tail.tail_volume_ratio,
        support_valid=support_valid,
        broken=bool(result.break_reason),
    )
    result.quality_score = result.score + result.compact_kline.score
    result.quality_tag = (
        "BOX_COMPACT_READY"
        if result.passed and result.compact_kline.passed
        else "NONE"
    )
    result.status = _classify_box_status(result, config)
    reason_names = {
        "width": "box:width_valid",
        "low_tests": "box:independent_low_tests",
        "center": "box:center_stable",
        "volume": "box:second_half_volume_contracted",
        "current_range": "box:current_close_in_range",
        "tail_volume": "box:tail_volume_dry",
        "selloff": "box:no_volume_selloff",
        "support": "box:key_support_valid",
        "break": "box:not_broken",
    }
    risk_names = {
        "width": "BOX_WIDTH_TOO_WIDE",
        "low_tests": "BOX_LOW_TESTS_INSUFFICIENT",
        "center": "BOX_CENTER_SHIFT_TOO_WEAK",
        "volume": "BOX_VOLUME_NOT_CONTRACTED",
        "current_range": "BOX_CURRENT_CLOSE_OUT_OF_RANGE",
        "tail_volume": "BOX_TAIL_VOLUME_NOT_DRY",
        "selloff": "BOX_VOLUME_SELLOFF",
        "support": "BOX_KEY_SUPPORT_BROKEN",
        "break": result.break_reason or "BOX_BROKEN",
    }
    for key, passed in conditions.items():
        target = result.reasons if passed else result.risk_tags
        target.append(reason_names[key] if passed else risk_names[key])
    return result


def _box_break_reason(
    box_data: list[dict],
    box_low: float,
    support: Strategy6Support,
    *,
    has_volume_selloff: bool,
    config: dict,
) -> str:
    current_close = float(box_data[-1]["close"])
    if current_close < box_low * (1 - config["broken_close_tolerance"]):
        return "CLOSE_BELOW_BOX_LOW_TOLERANCE"
    if len(box_data) >= 2 and all(float(row["close"]) < box_low for row in box_data[-2:]):
        return "TWO_CLOSES_BELOW_BOX_LOW"
    if has_volume_selloff and current_close < box_low:
        return "VOLUME_SELLOFF_BELOW_BOX_LOW"
    support_floor = max(
        float(support.key_support_price or 0),
        float(support.support_zone_low or 0),
    )
    if support_floor > 0 and current_close < support_floor:
        return "CLOSE_BELOW_KEY_SUPPORT"
    return ""


def _calculate_box_score(
    result: Strategy6BoxTail,
    *,
    tail_volume_ratio: float,
    support_valid: bool,
    broken: bool,
) -> int:
    width = result.box_width or float("inf")
    width_score = 4 if width <= 0.08 else 3 if width <= 0.12 else 2 if width <= 0.15 else 1 if width <= 0.18 else 0
    low_score = 4 if result.low_test_count >= 3 else 3 if result.low_test_count == 2 else 1 if result.low_test_count == 1 else 0
    center = result.center_shift if result.center_shift is not None else float("-inf")
    center_score = 4 if center >= 0.02 else 3 if center >= 0 else 2 if center >= -0.015 else 1 if center >= -0.03 else 0
    volume = result.volume_contraction_ratio if result.volume_contraction_ratio is not None else float("inf")
    volume_score = 4 if volume <= 0.60 else 3 if volume <= 0.70 else 2 if volume <= 0.85 else 1 if volume <= 1.0 else 0
    if broken:
        tail_support_score = 0
    elif tail_volume_ratio <= 0.60 and support_valid:
        tail_support_score = 4
    elif tail_volume_ratio <= 0.75 and support_valid:
        tail_support_score = 3
    elif tail_volume_ratio <= 0.75:
        tail_support_score = 2
    else:
        tail_support_score = 1
    return width_score + low_score + center_score + volume_score + tail_support_score


def _classify_box_status(result: Strategy6BoxTail, config: dict) -> str:
    if result.break_reason:
        return "BOX_BROKEN"
    if not result.passed:
        return "BOX_FORMING"
    if result.box_position <= config["support_ready_position_max"]:
        return "BOX_SUPPORT_READY"
    if result.box_position >= config["breakout_ready_position_min"]:
        return "BOX_BREAKOUT_READY"
    return "BOX_STABLE"


def evaluate_compact_kline(
    box_data: list[dict],
    *,
    atr5: float,
    atr20: float,
    tail_volume_ratio: float,
    premium_tail_volume_ratio_max: float,
    has_volume_selloff: bool,
    config: dict,
) -> Strategy6CompactKline:
    if not bool(config.get("enabled", True)):
        return Strategy6CompactKline(enabled=False)

    result = Strategy6CompactKline(enabled=True, atr5=atr5 or None, atr20=atr20 or None)
    window_days = int(config["window_days"])
    if len(box_data) < window_days:
        result.risk_tags.append("COMPACT_DATA_INSUFFICIENT")
        return result
    rows = box_data[-window_days:]
    if any(float(row.get("close") or 0) <= 0 for row in rows):
        result.risk_tags.append("COMPACT_INVALID_CLOSE")
        return result

    body_ratios = [abs(float(row["close"]) - float(row["open"])) / float(row["close"]) for row in rows]
    closes = [float(row["close"]) for row in rows]
    result.avg_body_ratio = round(mean(body_ratios), 6)
    result.max_body_ratio = round(max(body_ratios), 6)
    result.close_range = round(max(closes) / min(closes) - 1, 6)

    overlap_ratios: list[float] = []
    for previous, current in zip(rows[:-1], rows[1:]):
        ratio = calculate_kline_overlap_ratio(previous, current)
        if ratio is not None:
            overlap_ratios.append(ratio)
        else:
            result.risk_tags.append("COMPACT_ZERO_RANGE_KLINE")
    result.valid_overlap_pair_count = len(overlap_ratios)
    result.overlap_pair_count = sum(ratio >= config["min_overlap_ratio"] for ratio in overlap_ratios)
    result.premium_overlap_pair_count = sum(
        ratio >= config["premium_overlap_ratio"] for ratio in overlap_ratios
    )
    result.avg_overlap_ratio = round(mean(overlap_ratios), 6) if overlap_ratios else None

    gaps = []
    for previous, current in zip(rows[:-1], rows[1:]):
        previous_close = float(previous.get("close") or 0)
        if previous_close <= 0:
            result.risk_tags.append("COMPACT_INVALID_PREVIOUS_CLOSE")
            continue
        gaps.append(abs(float(current.get("open") or 0) - previous_close) / previous_close)
    result.gap_count = sum(gap > config["max_gap_ratio"] for gap in gaps)
    result.max_gap_ratio = round(max(gaps), 6) if gaps else None

    if atr20 <= 0:
        result.risk_tags.append("ATR_DATA_INSUFFICIENT")
    else:
        result.atr_contraction_ratio = round(atr5 / atr20, 6)

    conditions = {
        "body_avg": result.avg_body_ratio <= config["avg_body_ratio_max"],
        "body_max": result.max_body_ratio <= config["max_body_ratio_max"],
        "close_range": result.close_range <= config["close_range_max"],
        "overlap": (
            result.valid_overlap_pair_count >= config["min_overlap_pair_count"]
            and result.overlap_pair_count >= config["min_overlap_pair_count"]
        ),
        "gap": result.gap_count == 0 and len(gaps) == window_days - 1,
        "atr": (
            result.atr_contraction_ratio is not None
            and result.atr_contraction_ratio <= config["atr_contraction_ratio_max"]
        ),
        "selloff": not has_volume_selloff,
    }
    risk_by_condition = {
        "body_avg": "COMPACT_AVG_BODY_TOO_LARGE",
        "body_max": "COMPACT_MAX_BODY_TOO_LARGE",
        "close_range": "COMPACT_CLOSE_RANGE_TOO_WIDE",
        "overlap": "COMPACT_OVERLAP_INSUFFICIENT",
        "gap": "COMPACT_GAP_TOO_LARGE",
        "atr": "COMPACT_ATR_NOT_CONTRACTED",
        "selloff": "COMPACT_VOLUME_SELLOFF",
    }
    reason_by_condition = {
        "body_avg": "compact:small_average_body",
        "body_max": "compact:no_large_body",
        "close_range": "compact:close_concentrated",
        "overlap": "compact:range_overlap",
        "gap": "compact:no_large_gap",
        "atr": "compact:atr_contracted",
        "selloff": "compact:no_volume_selloff",
    }
    for key, passed in conditions.items():
        target = result.reasons if passed else result.risk_tags
        target.append(reason_by_condition[key] if passed else risk_by_condition[key])

    result.score = min(10, (
        2 * int(conditions["body_avg"])
        + int(conditions["body_max"])
        + 2 * int(conditions["close_range"])
        + 3 * int(conditions["overlap"])
        + int(conditions["atr"])
        + int(conditions["gap"])
    ))
    result.passed = all(conditions.values())
    result.premium = result.passed and all((
        result.avg_body_ratio <= config["premium_avg_body_ratio_max"],
        result.close_range <= config["premium_close_range_max"],
        result.premium_overlap_pair_count >= config["min_overlap_pair_count"],
        result.atr_contraction_ratio is not None
        and result.atr_contraction_ratio <= config["premium_atr_contraction_ratio_max"],
        tail_volume_ratio <= premium_tail_volume_ratio_max,
    ))
    result.quality_tag = "BOX_COMPACT_READY" if result.passed else "NONE"
    return result


def count_independent_box_low_tests(rows: list[dict], box_low: float, config: dict) -> int:
    matching = [
        index for index, row in enumerate(rows)
        if float(row["low"]) <= box_low * (1 + config["low_test_tolerance_up"])
        and float(row["close"]) >= box_low * (1 - config["low_test_close_tolerance_down"])
    ]
    return _count_independent_indexes(matching)


def count_independent_box_high_tests(rows: list[dict], box_high: float, config: dict) -> int:
    matching = [
        index for index, row in enumerate(rows)
        if float(row["high"]) >= box_high * (1 - config["low_test_tolerance_up"])
        and float(row["close"]) <= box_high * (1 + config["low_test_close_tolerance_down"])
    ]
    return _count_independent_indexes(matching)


def calculate_kline_overlap_ratio(previous: dict, current: dict) -> float | None:
    return _shared_overlap_ratio(previous, current)


def _count_independent_indexes(indexes: list[int]) -> int:
    count = 0
    last_counted = -3
    for index in indexes:
        if index - last_counted >= 3:
            count += 1
            last_counted = index
    return count
