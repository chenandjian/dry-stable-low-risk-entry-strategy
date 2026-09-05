from __future__ import annotations

import math
import statistics
from functools import lru_cache

from scanner.clean_k_analysis import (
    CleanKInputError,
    analyze_clean_k,
    resolve_clean_k_config,
    resolve_clean_k_period,
)


DEFAULT_CLEAN_K_V2_CONFIG = {
    "directional_expansion_range_atr": 1.20,
    "directional_expansion_body_ratio": 0.55,
    "directional_expansion_close_edge": 0.75,
    "directional_expansion_two_side_wick_atr": 0.45,
    "conflict_expansion_range_atr": 1.20,
    "conflict_expansion_two_side_wick_atr": 0.60,
    "conflict_expansion_body_ratio": 0.35,
    "conflict_expansion_wick_atr": 0.90,
    "gap_reversal_min_atr": 0.50,
    "dirty_extreme_range_atr_v2": 1.80,
    "dirty_extreme_bar_score_v2": 50.0,
    "pivot_window": 2,
    "min_segment_days": 5,
    "max_segments": 3,
    "complexity_penalty_per_cut": 3.0,
    "base_to_trend_bonus": 8.0,
    "contraction_to_trend_bonus": 10.0,
    "trend_to_base_bonus": 5.0,
    "trend_pullback_trend_bonus": 8.0,
    "max_transition_bonus": 10.0,
    "max_pullback_ratio": 0.70,
    "window_clean_score": 70.0,
    "window_min_structure_score": 65.0,
    "current_clean_score": 75.0,
    "current_min_structure_score": 65.0,
    "min_current_days": 5,
    "max_dirty_ratio": 0.10,
    "chaotic_move_atr": 0.75,
    "chaotic_reversal_rate": 0.60,
    "current_min_score_improvement": 8.0,
    "current_boundary_move_atr": 0.80,
    "trend_er_weight": 0.25,
    "trend_r2_weight": 0.20,
    "trend_progress_weight": 0.35,
    "trend_retracement_weight": 0.20,
    "window_structure_weight": 0.55,
    "window_range_rhythm_weight": 0.15,
    "window_extreme_control_weight": 0.15,
    "window_median_bar_weight": 0.15,
    "current_structure_weight": 0.60,
    "current_range_rhythm_weight": 0.15,
    "current_extreme_control_weight": 0.15,
    "current_median_bar_weight": 0.10,
}


def resolve_clean_k_v2_config(raw: dict | None = None) -> dict:
    raw = raw or {}
    cfg = {**resolve_clean_k_config(raw), **DEFAULT_CLEAN_K_V2_CONFIG}
    for key in DEFAULT_CLEAN_K_V2_CONFIG:
        if key in raw:
            cfg[key] = raw[key]
    try:
        for key in DEFAULT_CLEAN_K_V2_CONFIG:
            if key in {"pivot_window", "min_segment_days", "max_segments", "min_current_days"}:
                cfg[key] = int(cfg[key])
            else:
                cfg[key] = float(cfg[key])
    except (TypeError, ValueError) as exc:
        raise CleanKInputError(f"invalid clean-k V2 configuration: {exc}") from exc
    if cfg["pivot_window"] < 1:
        raise CleanKInputError("pivot_window must be positive")
    if cfg["min_segment_days"] < 5:
        raise CleanKInputError("min_segment_days must be at least 5")
    if cfg["max_segments"] not in {1, 2, 3}:
        raise CleanKInputError("max_segments must be between 1 and 3")
    if cfg["min_current_days"] < 5:
        raise CleanKInputError("min_current_days must be at least 5")
    ratio_keys = (
        "directional_expansion_body_ratio",
        "directional_expansion_close_edge",
        "max_pullback_ratio",
        "max_dirty_ratio",
        "chaotic_reversal_rate",
    )
    if any(not 0 <= cfg[key] <= 1 for key in ratio_keys):
        raise CleanKInputError("clean-k V2 ratio thresholds must be between 0 and 1")
    weight_groups = (
        ("trend_er_weight", "trend_r2_weight", "trend_progress_weight", "trend_retracement_weight"),
        ("window_structure_weight", "window_range_rhythm_weight", "window_extreme_control_weight", "window_median_bar_weight"),
        ("current_structure_weight", "current_range_rhythm_weight", "current_extreme_control_weight", "current_median_bar_weight"),
    )
    for keys in weight_groups:
        if any(cfg[key] < 0 for key in keys) or not math.isclose(sum(cfg[key] for key in keys), 1.0, abs_tol=1e-9):
            raise CleanKInputError(f"clean-k V2 weights must be non-negative and sum to 1: {keys}")
    return cfg


def analyze_clean_k_v2(
    source_rows: list[dict],
    *,
    period: int = 20,
    config: dict | None = None,
    stock_code: str = "",
    target_trade_date: str | None = None,
) -> dict:
    cfg = resolve_clean_k_v2_config(config)
    period = resolve_clean_k_period(period, cfg)
    legacy = analyze_clean_k(
        source_rows,
        period=period,
        config=cfg,
        stock_code=stock_code,
        target_trade_date=target_trade_date,
    )
    target_dates = [item["tradeDate"] for item in legacy["barMetrics"]]
    row_by_date = {str(row.get("date")): dict(row) for row in source_rows if row.get("date")}
    target_rows = [row_by_date[day] for day in target_dates]
    previous_by_date = _previous_effective_rows(source_rows, target_trade_date)
    metrics = [
        _classify_bar_v2(
            dict(metric),
            row_by_date[metric["tradeDate"]],
            previous_by_date.get(metric["tradeDate"]),
            cfg,
        )
        for metric in legacy["barMetrics"]
    ]

    scorer = _SegmentScorer(target_rows, metrics, cfg)
    single = scorer.score(0, period)
    composite = _search_composite_structure(scorer, target_rows, cfg)
    chosen = (
        composite
        if composite
        and not single["chaotic"]
        and composite["finalScore"] >= single["structureScore"]
        else None
    )
    if chosen:
        window_structure_score = chosen["finalScore"]
        window_structure = chosen["structureLabel"]
        segments = chosen["segments"]
        transitions = chosen["transitions"]
    else:
        window_structure_score = single["structureScore"]
        window_structure = single["structureType"]
        segments = [single]
        transitions = []
    if window_structure == "MIXED":
        window_structure = "CHAOTIC"

    avg_bar_score, median_bar_score = _bar_score_stats(metrics)
    full_contraction = single["contractionScore"]
    range_rhythm = max(_range_consistency_score(metrics), full_contraction)
    dirty_count = sum(bool(item["dirtyExtremeBar"]) for item in metrics)
    extreme_control = _extreme_control_score(dirty_count, len(metrics))
    window_score = (
        window_structure_score * cfg["window_structure_weight"]
        + range_rhythm * cfg["window_range_rhythm_weight"]
        + extreme_control * cfg["window_extreme_control_weight"]
        + median_bar_score * cfg["window_median_bar_weight"]
    )
    window_blocks = _window_blocking_reasons(
        score=window_score,
        structure_score=window_structure_score,
        confidence=legacy["confidence"],
        structure=window_structure,
        dirty_count=dirty_count,
        period=period,
        cfg=cfg,
    )
    window_is_clean = not window_blocks

    current = _detect_current_segment(
        scorer,
        target_rows,
        metrics,
        cfg,
        window_is_clean=window_is_clean,
        window_score=window_score,
        max_current_days=segments[-1]["days"] if chosen else period,
    )
    current["level"] = _clean_level(current["score"], cfg["current_clean_score"])
    window = {
        "isClean": window_is_clean,
        "score": _round(window_score),
        "level": _clean_level(window_score, cfg["window_clean_score"]),
        "structure": window_structure,
        "structureScore": _round(window_structure_score),
        "direction": segments[-1]["direction"] if chosen else single["direction"],
        "startDate": target_rows[0]["date"],
        "endDate": target_rows[-1]["date"],
        "blockingReasons": window_blocks,
    }
    bar_stats = {
        "directionalExpansionCount": _count_type(metrics, "DIRECTIONAL_EXPANSION"),
        "conflictExpansionCount": _count_type(metrics, "CONFLICT_EXPANSION"),
        "gapReversalExpansionCount": _count_type(metrics, "GAP_REVERSAL_EXPANSION"),
        "microRangeCount": _count_type(metrics, "MICRO_RANGE"),
        "eventBarCount": _count_type(metrics, "ONE_PRICE_EVENT"),
        "dirtyExtremeCount": dirty_count,
    }
    risks = _build_risk_flags(
        legacy, window, current, bar_stats, target_rows
    )
    reasons = _build_reasons(window, current, bar_stats, transitions)
    result = dict(legacy)
    result.update({
        "modelVersion": "CLEAN_K_V2",
        "window": window,
        "current": current,
        "barStats": bar_stats,
        "segments": [_public_segment(item) for item in segments],
        "transitions": transitions,
        "structureScores": {
            "trendCleanScore": _round(single["trendScore"]),
            "robustBaseCleanScore": _round(single["baseScore"]),
            "legacyBaseCleanScore": legacy["baseCleanScore"],
            "contractionCleanScore": _round(single["contractionScore"]),
            "structureProgressScore": _round(single["progressScore"]),
            "retracementDisciplineScore": _round(single["retracementScore"]),
        },
        "legacyV1": {
            "isClean": legacy["isClean"],
            "score": legacy["cleanKScore"],
            "structure": legacy["structureMode"],
            "structureScore": legacy["structureScore"],
        },
        "isClean": window["isClean"],
        "cleanKScore": window["score"],
        "cleanLevel": window["level"],
        "structureMode": window["structure"],
        "structureScore": window["structureScore"],
        "sequenceCleanScore": window["score"],
        "trendCleanScore": _round(single["trendScore"]),
        "baseCleanScore": _round(single["baseScore"]),
        "contractionCleanScore": _round(single["contractionScore"]),
        "rangeRhythmScore": _round(range_rhythm),
        "extremeControlScore": _round(extreme_control),
        "avgBarCleanScore": _round(avg_bar_score),
        "dirtyExtremeCount": dirty_count,
        "reasons": reasons,
        "riskFlags": risks,
        "barMetrics": metrics,
    })
    return result


class _SegmentScorer:
    def __init__(self, rows: list[dict], metrics: list[dict], cfg: dict):
        self.rows = rows
        self.metrics = metrics
        self.cfg = cfg

    @lru_cache(maxsize=None)
    def score(self, start: int, end: int) -> dict:
        rows = self.rows[start:end]
        metrics = self.metrics[start:end]
        direction = _direction(rows)
        trend, progress, retracement = _trend_score(rows, self.cfg)
        base, robust_high, robust_low = _robust_base_score(rows, metrics)
        contraction = _contraction_score(rows, metrics)
        chaotic, reversal_rate = _significant_reversal_disorder(rows, metrics, self.cfg)
        choices = {
            f"TREND_{direction}": trend,
            "BASE": base,
            "CONTRACTION": contraction,
        }
        structure_type, structure_score = max(choices.items(), key=lambda item: item[1])
        if chaotic:
            structure_type = "MIXED"
            structure_score = min(structure_score, 40.0)
        elif structure_score < 45:
            structure_type = "MIXED"
        return {
            "startIndex": start,
            "endIndex": end - 1,
            "startDate": rows[0]["date"],
            "endDate": rows[-1]["date"],
            "days": len(rows),
            "structureType": structure_type,
            "structureScore": structure_score,
            "trendScore": trend,
            "baseScore": base,
            "contractionScore": contraction,
            "progressScore": progress,
            "retracementScore": retracement,
            "direction": direction,
            "robustHigh": robust_high,
            "robustLow": robust_low,
            "chaotic": chaotic,
            "significantReversalRate": reversal_rate,
        }


def _previous_effective_rows(
    source_rows: list[dict], target_trade_date: str | None
) -> dict[str, dict]:
    eligible = sorted(
        (
            dict(row) for row in source_rows
            if row.get("date") and (not target_trade_date or row["date"] <= target_trade_date)
        ),
        key=lambda row: row["date"],
    )
    result = {}
    previous = None
    for row in eligible:
        if _is_suspended(row):
            continue
        if previous is not None:
            result[row["date"]] = previous
        previous = row
    return result


def _classify_bar_v2(metric: dict, row: dict, previous: dict | None, cfg: dict) -> dict:
    if metric["eventBar"]:
        return metric
    range_atr = float(metric["intradayRangeAtr"])
    body_ratio = float(metric["bodyRatio"])
    two_side_wick_atr = 2 * min(
        float(metric["upperWickRatio"]), float(metric["lowerWickRatio"])
    ) * range_atr
    close = float(row["close"])
    high = float(row["high"])
    low = float(row["low"])
    price_range = high - low
    close_edge = max((close - low) / price_range, (high - close) / price_range)
    gap_reversal = False
    if previous is not None and float(metric["gapAtr"]) >= cfg["gap_reversal_min_atr"]:
        gap_direction = _sign(float(row["open"]) - float(previous["close"]))
        intraday_direction = _sign(close - float(row["open"]))
        gap_reversal = bool(gap_direction and intraday_direction == -gap_direction)

    directional = (
        range_atr >= cfg["directional_expansion_range_atr"]
        and body_ratio >= cfg["directional_expansion_body_ratio"]
        and close_edge >= cfg["directional_expansion_close_edge"]
        and two_side_wick_atr <= cfg["directional_expansion_two_side_wick_atr"]
    )
    conflict = (
        range_atr >= cfg["conflict_expansion_range_atr"]
        and (
            two_side_wick_atr >= cfg["conflict_expansion_two_side_wick_atr"]
            or (
                body_ratio <= cfg["conflict_expansion_body_ratio"]
                and float(metric["wickAtr"]) >= cfg["conflict_expansion_wick_atr"]
            )
        )
    )
    if gap_reversal and range_atr >= cfg["directional_expansion_range_atr"]:
        structure = "GAP_REVERSAL_EXPANSION"
        dirty = True
    elif conflict:
        structure = "CONFLICT_EXPANSION"
        dirty = True
    elif directional:
        structure = "DIRECTIONAL_EXPANSION"
        dirty = False
        metric["barCleanScore"] = max(float(metric["barCleanScore"]), 75.0)
    else:
        structure = _normalise_v1_structure(metric["barStructureType"])
        dirty = (
            range_atr > cfg["dirty_extreme_range_atr_v2"]
            and float(metric["barCleanScore"]) < cfg["dirty_extreme_bar_score_v2"]
        )
    metric.update({
        "barStructureType": structure,
        "dirtyExtremeBar": dirty,
        "closeEdgeScore": _round(close_edge, 6),
        "twoSideWickAtr": _round(two_side_wick_atr, 6),
        "gapReversal": gap_reversal,
    })
    return metric


def _normalise_v1_structure(value: str) -> str:
    if value in {
        "MICRO_RANGE", "ONE_SIDE_UPPER_REJECTION", "ONE_SIDE_LOWER_REJECTION",
        "TWO_SIDE_CONFLICT", "ONE_PRICE_EVENT",
    }:
        return value
    return "NORMAL_BAR"


def _search_composite_structure(
    scorer: _SegmentScorer, rows: list[dict], cfg: dict
) -> dict | None:
    count = len(rows)
    minimum = cfg["min_segment_days"]
    best = None
    if cfg["max_segments"] >= 2 and count >= minimum * 2:
        for cut in range(minimum, count - minimum + 1):
            left = scorer.score(0, cut)
            right = scorer.score(cut, count)
            transition = _classify_two_segment_transition(left, right, rows, cfg)
            if transition is None:
                continue
            bonus = _transition_bonus(transition, cfg)
            score = _weighted_segment_score([left, right]) + bonus - cfg["complexity_penalty_per_cut"]
            candidate = {
                "segments": [left, right],
                "transitions": [transition],
                "weightedSegmentScore": _weighted_segment_score([left, right]),
                "transitionBonus": bonus,
                "complexityPenalty": cfg["complexity_penalty_per_cut"],
                "finalScore": min(score, 100.0),
                "structureLabel": transition,
            }
            best = _better_composite(best, candidate)
    if cfg["max_segments"] >= 3 and count >= minimum * 3:
        for cut1 in range(minimum, count - minimum * 2 + 1):
            for cut2 in range(cut1 + minimum, count - minimum + 1):
                segments = [
                    scorer.score(0, cut1),
                    scorer.score(cut1, cut2),
                    scorer.score(cut2, count),
                ]
                if not _is_trend_pullback_trend(segments, rows, cfg):
                    continue
                bonus = cfg["trend_pullback_trend_bonus"]
                penalty = cfg["complexity_penalty_per_cut"] * 2
                candidate = {
                    "segments": segments,
                    "transitions": ["TREND_PULLBACK_TREND"],
                    "weightedSegmentScore": _weighted_segment_score(segments),
                    "transitionBonus": bonus,
                    "complexityPenalty": penalty,
                    "finalScore": min(_weighted_segment_score(segments) + bonus - penalty, 100.0),
                    "structureLabel": "TREND_PULLBACK_TREND",
                }
                best = _better_composite(best, candidate)
    return best


def _classify_two_segment_transition(
    left: dict, right: dict, rows: list[dict], cfg: dict
) -> str | None:
    right_type = right["structureType"]
    if left["structureType"] in {"BASE", "CONTRACTION"} and right_type.startswith("TREND_"):
        right_rows = rows[right["startIndex"]:right["endIndex"] + 1]
        if right_type == "TREND_UP":
            confirmed = float(right_rows[-1]["close"]) > left["robustHigh"]
        else:
            confirmed = float(right_rows[-1]["close"]) < left["robustLow"]
        if confirmed:
            return "BASE_TO_TREND" if left["structureType"] == "BASE" else "CONTRACTION_TO_TREND"
    if left["structureType"].startswith("TREND_") and right_type == "BASE":
        if left["direction"] == right["direction"] or right["direction"] == "FLAT":
            return "TREND_TO_BASE"
    return None


def _is_trend_pullback_trend(segments: list[dict], rows: list[dict], cfg: dict) -> bool:
    first, middle, last = segments
    if not first["structureType"].startswith("TREND_"):
        return False
    if last["structureType"] != first["structureType"]:
        return False
    if middle["structureType"] not in {"TREND_UP", "TREND_DOWN", "BASE", "MIXED"}:
        return False
    first_rows = rows[first["startIndex"]:first["endIndex"] + 1]
    middle_rows = rows[middle["startIndex"]:middle["endIndex"] + 1]
    last_rows = rows[last["startIndex"]:last["endIndex"] + 1]
    if first["direction"] == "UP":
        leg = max(float(row["high"]) for row in first_rows) - min(float(row["low"]) for row in first_rows)
        retracement = (
            max(float(row["high"]) for row in first_rows)
            - min(float(row["low"]) for row in middle_rows)
        ) / max(leg, 1e-10)
        recovered = float(last_rows[-1]["close"]) > max(float(row["high"]) for row in first_rows)
        middle_opposes = middle["direction"] in {"DOWN", "FLAT"}
    else:
        leg = max(float(row["high"]) for row in first_rows) - min(float(row["low"]) for row in first_rows)
        retracement = (
            max(float(row["high"]) for row in middle_rows)
            - min(float(row["low"]) for row in first_rows)
        ) / max(leg, 1e-10)
        recovered = float(last_rows[-1]["close"]) < min(float(row["low"]) for row in first_rows)
        middle_opposes = middle["direction"] in {"UP", "FLAT"}
    return middle_opposes and 0 <= retracement <= cfg["max_pullback_ratio"] and recovered


def _detect_current_segment(
    scorer: _SegmentScorer,
    rows: list[dict],
    metrics: list[dict],
    cfg: dict,
    *,
    window_is_clean: bool,
    window_score: float,
    max_current_days: int,
) -> dict:
    count = len(rows)
    minimum = min(cfg["min_current_days"], count)
    candidates = []
    for days in range(minimum, min(count, max_current_days) + 1):
        start = count - days
        segment = scorer.score(start, count)
        current_metrics = metrics[start:]
        _, median_score = _bar_score_stats(current_metrics)
        rhythm = max(_range_consistency_score(current_metrics), segment["contractionScore"])
        dirty_count = sum(bool(item["dirtyExtremeBar"]) for item in current_metrics)
        extreme = _extreme_control_score(dirty_count, len(current_metrics))
        score = (
            segment["structureScore"] * cfg["current_structure_weight"]
            + rhythm * cfg["current_range_rhythm_weight"]
            + extreme * cfg["current_extreme_control_weight"]
            + median_score * cfg["current_median_bar_weight"]
        )
        blocks = _current_blocking_reasons(
            rows=rows,
            metrics=metrics,
            start=start,
            days=days,
            score=score,
            segment=segment,
            current_metrics=current_metrics,
            dirty_count=dirty_count,
            cfg=cfg,
            window_is_clean=window_is_clean,
            window_score=window_score,
        )
        candidates.append((days, score, segment, not blocks, blocks))
    valid_candidates = [item for item in candidates if item[3]]
    if valid_candidates:
        days, score, segment, _, blocks = max(valid_candidates, key=lambda item: (item[0], item[1]))
        is_clean = True
        clean_days = days
    else:
        days, score, segment, _, blocks = max(
            candidates,
            key=lambda item: (item[1] + min(item[0] / count * 10, 10), item[0]),
        )
        is_clean = False
        clean_days = 0
    return {
        "isClean": is_clean,
        "score": _round(score),
        "days": clean_days,
        "evaluatedDays": days,
        "structure": segment["structureType"] if segment["structureType"] != "MIXED" else "CHAOTIC",
        "structureScore": _round(segment["structureScore"]),
        "direction": segment["direction"],
        "startDate": rows[-days]["date"],
        "endDate": rows[-1]["date"],
        "blockingReasons": blocks,
    }


def _trend_score(rows: list[dict], cfg: dict) -> tuple[float, float, float]:
    closes = [float(row["close"]) for row in rows]
    path = sum(abs(closes[index] - closes[index - 1]) for index in range(1, len(closes)))
    er = abs(closes[-1] - closes[0]) / path if path > 0 else 0.0
    er_score = _linear_score(er, 0.20, 0.65)
    r2_score = _linear_score(_linear_regression_r2([math.log(value) for value in closes]), 0.35, 0.80)
    progress = _structure_progress_score(rows, cfg["pivot_window"])
    retracement = _retracement_discipline_score(rows)
    return (
        er_score * cfg["trend_er_weight"]
        + r2_score * cfg["trend_r2_weight"]
        + progress * cfg["trend_progress_weight"]
        + retracement * cfg["trend_retracement_weight"]
    ), progress, retracement


def _structure_progress_score(rows: list[dict], pivot_window: int) -> float:
    direction = _direction(rows)
    highs, lows = _swing_values(rows, pivot_window)
    if len(highs) >= 2 and len(lows) >= 2:
        high_ratio = _ordered_ratio(highs, direction)
        low_ratio = _ordered_ratio(lows, direction)
    else:
        high_ratio = _ordered_ratio([float(row["high"]) for row in rows], direction)
        low_ratio = _ordered_ratio([float(row["low"]) for row in rows], direction)
    return (high_ratio + low_ratio) * 50


def _swing_values(rows: list[dict], window: int) -> tuple[list[float], list[float]]:
    highs = []
    lows = []
    for index in range(window, len(rows) - window):
        high = float(rows[index]["high"])
        low = float(rows[index]["low"])
        neighbours = rows[index - window:index] + rows[index + 1:index + window + 1]
        if all(high > float(row["high"]) for row in neighbours):
            highs.append(high)
        if all(low < float(row["low"]) for row in neighbours):
            lows.append(low)
    return highs, lows


def _ordered_ratio(values: list[float], direction: str) -> float:
    if len(values) < 2 or direction == "FLAT":
        return 0.5
    if direction == "UP":
        ordered = sum(right >= left for left, right in zip(values, values[1:]))
    else:
        ordered = sum(right <= left for left, right in zip(values, values[1:]))
    return ordered / (len(values) - 1)


def _retracement_discipline_score(rows: list[dict]) -> float:
    direction = _direction(rows)
    closes = [float(row["close"]) for row in rows]
    adverse = []
    if direction == "UP":
        peak = closes[0]
        leg_low = closes[0]
        for close in closes[1:]:
            if close >= peak:
                peak = close
            else:
                adverse.append((peak - close) / max(peak - leg_low, abs(peak) * 0.01))
            leg_low = min(leg_low, close)
    elif direction == "DOWN":
        trough = closes[0]
        leg_high = closes[0]
        for close in closes[1:]:
            if close <= trough:
                trough = close
            else:
                adverse.append((close - trough) / max(leg_high - trough, abs(trough) * 0.01))
            leg_high = max(leg_high, close)
    if not adverse:
        return 100.0 if direction != "FLAT" else 50.0
    return _inverse_linear_score(statistics.median(adverse), 0.45, 0.80)


def _robust_base_score(rows: list[dict], metrics: list[dict]) -> tuple[float, float, float]:
    highs = sorted(float(row["high"]) for row in rows)
    lows = sorted(float(row["low"]) for row in rows)
    if len(rows) <= 15 and len(rows) >= 3:
        robust_high = highs[-2]
        robust_low = lows[1]
    else:
        robust_high = _percentile(highs, 0.90)
        robust_low = _percentile(lows, 0.10)
    atr_median = statistics.median(float(item["atr14Prev"]) for item in metrics)
    width_atr = max(0.0, robust_high - robust_low) / atr_median
    drift_atr = abs(float(rows[-1]["close"]) - float(rows[0]["close"])) / atr_median
    score = _inverse_linear_score(width_atr, 2.0, 4.5) * 0.70 + _inverse_linear_score(drift_atr, 0.7, 2.2) * 0.30
    return score, robust_high, robust_low


def _contraction_score(rows: list[dict], metrics: list[dict]) -> float:
    if len(rows) < 6:
        return 0.0
    ranges = [float(item["intradayRangeAtr"]) for item in metrics]
    first, last = _outer_thirds(ranges)
    first_median = statistics.median(first)
    daily_ratio = statistics.median(last) / first_median if first_median > 0 else 1.0
    daily_score = _inverse_linear_score(daily_ratio, 0.60, 1.05)
    rolling_score = 0.0
    if len(rows) >= 9:
        rolling = []
        for index in range(4, len(rows)):
            window_rows = rows[index - 4:index + 1]
            window_metrics = metrics[index - 4:index + 1]
            atr = statistics.median(float(item["atr14Prev"]) for item in window_metrics)
            rolling.append((max(float(row["high"]) for row in window_rows) - min(float(row["low"]) for row in window_rows)) / atr)
        rolling_first, rolling_last = _outer_thirds(rolling)
        denominator = statistics.median(rolling_first)
        ratio = statistics.median(rolling_last) / denominator if denominator > 0 else 1.0
        rolling_score = _inverse_linear_score(ratio, 0.65, 1.05)
    trend_score = _inverse_linear_score(_spearman(ranges), -0.60, 0.0)
    if len(rows) < 9:
        return daily_score * 0.70 + trend_score * 0.30
    return daily_score * 0.45 + rolling_score * 0.35 + trend_score * 0.20


def _range_consistency_score(metrics: list[dict]) -> float:
    values = [float(item["intradayRangeAtr"]) for item in metrics]
    median_value = statistics.median(values)
    if median_value <= 0:
        return 100.0
    mad = statistics.median(abs(value - median_value) for value in values)
    return _inverse_linear_score(mad / median_value, 0.15, 0.60)


def _significant_reversal_disorder(
    rows: list[dict], metrics: list[dict], cfg: dict
) -> tuple[bool, float]:
    signs = []
    for index in range(1, len(rows)):
        atr = max(float(metrics[index]["atr14Prev"]), 1e-10)
        move_atr = (
            float(rows[index]["close"]) - float(rows[index - 1]["close"])
        ) / atr
        if abs(move_atr) >= cfg["chaotic_move_atr"]:
            signs.append(_sign(move_atr))
    if len(signs) < 4:
        return False, 0.0
    reversals = sum(left != right for left, right in zip(signs, signs[1:]))
    reversal_rate = reversals / (len(signs) - 1)
    return reversal_rate >= cfg["chaotic_reversal_rate"], reversal_rate


def _has_directional_break(
    rows: list[dict], metrics: list[dict], direction: str
) -> bool:
    if direction == "FLAT":
        return False
    absolute_moves = [
        abs(float(rows[index]["close"]) - float(rows[index - 1]["close"]))
        for index in range(1, len(rows))
    ]
    local_move = statistics.median(absolute_moves) if absolute_moves else 0.0
    for index in range(1, len(rows)):
        atr = max(float(metrics[index]["atr14Prev"]), 1e-10)
        move = float(rows[index]["close"]) - float(rows[index - 1]["close"])
        break_size = min(atr, max(local_move * 4, atr * 0.35))
        if direction == "UP" and move <= -break_size:
            return True
        if direction == "DOWN" and move >= break_size:
            return True
    return False


def _bar_score_stats(metrics: list[dict]) -> tuple[float, float]:
    scores = [float(item["barCleanScore"]) for item in metrics if item["barCleanScore"] is not None]
    if not scores:
        return 0.0, 0.0
    return statistics.fmean(scores), statistics.median(scores)


def _trailing_event_count(metrics: list[dict]) -> int:
    count = 0
    for item in reversed(metrics):
        if not item["eventBar"]:
            break
        count += 1
    return count


def _window_blocking_reasons(
    *, score: float, structure_score: float, confidence: float, structure: str,
    dirty_count: int, period: int, cfg: dict,
) -> list[str]:
    reasons = []
    if score < cfg["window_clean_score"]:
        reasons.append("WINDOW_SCORE_BELOW_THRESHOLD")
    if structure_score < cfg["window_min_structure_score"]:
        reasons.append("WINDOW_STRUCTURE_SCORE_BELOW_THRESHOLD")
    if confidence < cfg["min_confidence"]:
        reasons.append("LOW_CONFIDENCE")
    if structure == "CHAOTIC":
        reasons.append("CHAOTIC_STRUCTURE")
    if dirty_count > max(1, math.floor(period * cfg["max_dirty_ratio"])):
        reasons.append("TOO_MANY_CONFLICT_BARS")
    return reasons


def _current_blocking_reasons(
    *, rows: list[dict], metrics: list[dict], start: int, days: int, score: float,
    segment: dict, current_metrics: list[dict], dirty_count: int, cfg: dict,
    window_is_clean: bool, window_score: float,
) -> list[str]:
    reasons = []
    if score < cfg["current_clean_score"]:
        reasons.append("CURRENT_SCORE_BELOW_THRESHOLD")
    if segment["structureScore"] < cfg["current_min_structure_score"]:
        reasons.append("CURRENT_STRUCTURE_SCORE_BELOW_THRESHOLD")
    if segment["structureType"] == "MIXED" or segment["chaotic"]:
        reasons.append("CHAOTIC_STRUCTURE")
    if sum(item["barCleanScore"] is not None for item in current_metrics) / days < cfg["min_confidence"]:
        reasons.append("LOW_CONFIDENCE")
    if _trailing_event_count(current_metrics) > max(1, math.floor(days * cfg["max_dirty_ratio"])):
        reasons.append("TOO_MANY_TRAILING_EVENTS")
    if dirty_count > max(1, math.floor(days * cfg["max_dirty_ratio"])):
        reasons.append("TOO_MANY_CONFLICT_BARS")
    if _has_directional_break(rows[start:], current_metrics, segment["direction"]):
        reasons.append("DIRECTIONAL_STRUCTURE_BREAK")
    if not window_is_clean:
        if (
            start <= 0
            or score < window_score + cfg["current_min_score_improvement"]
            or not _has_current_boundary_evidence(rows, metrics, start, cfg)
        ):
            reasons.append("NO_CONFIRMED_CURRENT_BOUNDARY")
    return list(dict.fromkeys(reasons))


def _has_current_boundary_evidence(
    rows: list[dict], metrics: list[dict], start: int, cfg: dict
) -> bool:
    if start <= 0:
        return False
    if metrics[start - 1]["dirtyExtremeBar"] or metrics[start]["dirtyExtremeBar"]:
        return True
    atr = max(float(metrics[start]["atr14Prev"]), 1e-10)
    boundary_move = abs(
        float(rows[start]["close"]) - float(rows[start - 1]["close"])
    ) / atr
    return boundary_move >= cfg["current_boundary_move_atr"]


def _extreme_control_score(dirty_count: int, count: int) -> float:
    if count <= 0:
        return 0.0
    return 100 * (1 - min((dirty_count / count) / 0.30, 1))


def _weighted_segment_score(segments: list[dict]) -> float:
    total = sum(item["days"] for item in segments)
    return sum(item["structureScore"] * item["days"] for item in segments) / total


def _transition_bonus(transition: str, cfg: dict) -> float:
    key = {
        "BASE_TO_TREND": "base_to_trend_bonus",
        "CONTRACTION_TO_TREND": "contraction_to_trend_bonus",
        "TREND_TO_BASE": "trend_to_base_bonus",
    }[transition]
    return min(cfg[key], cfg["max_transition_bonus"])


def _better_composite(current: dict | None, candidate: dict) -> dict:
    if current is None or candidate["finalScore"] > current["finalScore"]:
        return candidate
    return current


def _public_segment(segment: dict) -> dict:
    keys = (
        "startIndex", "endIndex", "startDate", "endDate", "days",
        "structureType", "structureScore", "trendScore", "baseScore",
        "contractionScore", "progressScore", "retracementScore",
    )
    return {
        key: _round(segment[key]) if isinstance(segment[key], float) else segment[key]
        for key in keys
    }


def _build_risk_flags(
    legacy: dict, window: dict, current: dict, stats: dict, rows: list[dict]
) -> list[str]:
    preserved = [
        flag for flag in legacy["riskFlags"]
        if flag in {"STALE_LOCAL_DATA", "LOW_CONFIDENCE", "ONE_PRICE_EVENTS", "SUSPENDED_BARS_EXCLUDED"}
    ]
    if window["structure"] == "CHAOTIC":
        preserved.append("CHAOTIC_WINDOW_STRUCTURE")
    if stats["conflictExpansionCount"]:
        preserved.append("CONFLICT_EXPANSION_BARS")
    if stats["gapReversalExpansionCount"]:
        preserved.append("GAP_REVERSAL_EXPANSION_BARS")
    if current["isClean"] and _direction(rows[-current["days"]:]) == "DOWN":
        preserved.append("CURRENT_CLEAN_DOWNTREND")
    return list(dict.fromkeys(preserved))


def _build_reasons(window: dict, current: dict, stats: dict, transitions: list[str]) -> list[str]:
    labels = {
        "BASE_TO_TREND": "平台到趋势的有序转换",
        "CONTRACTION_TO_TREND": "收缩到趋势的有序转换",
        "TREND_TO_BASE": "趋势进入平台消化",
        "TREND_PULLBACK_TREND": "趋势、受控回撤、趋势恢复",
        "CHAOTIC": "无明确主导结构的宽幅混合走势",
    }
    reasons = [
        f"最近窗口识别为{labels.get(window['structure'], window['structure'])}（{window['structureScore']:.1f}分）"
    ]
    if current["isClean"]:
        reasons.append(f"当前连续{current['days']}个交易日结构有序（{current['score']:.1f}分）")
    if stats["directionalExpansionCount"]:
        reasons.append(f"{stats['directionalExpansionCount']}根大幅K属于方向型扩张，不计为高噪音")
    actual_conflicts = stats["conflictExpansionCount"] + stats["gapReversalExpansionCount"]
    reasons.append(f"真实冲突型扩张K线{actual_conflicts}根")
    if transitions:
        reasons.append("复合结构只采用有价格证据确认的合法转换")
    return reasons


def _clean_level(score: float, clean_threshold: float) -> str:
    if score >= 85:
        return "EXTREMELY_CLEAN"
    if score >= clean_threshold:
        return "CLEAN"
    if score >= 60:
        return "ACCEPTABLE"
    if score >= 50:
        return "NOISY"
    return "VERY_NOISY"


def _count_type(metrics: list[dict], value: str) -> int:
    return sum(item["barStructureType"] == value for item in metrics)


def _direction(rows: list[dict]) -> str:
    change = float(rows[-1]["close"]) / float(rows[0]["close"]) - 1
    if change > 0.005:
        return "UP"
    if change < -0.005:
        return "DOWN"
    return "FLAT"


def _is_suspended(row: dict) -> bool:
    try:
        return (
            float(row.get("volume", 0)) == 0
            and float(row.get("turnover", 0) or 0) == 0
            and float(row["open"]) == float(row["high"]) == float(row["low"]) == float(row["close"])
        )
    except (KeyError, TypeError, ValueError):
        return False


def _percentile(values: list[float], quantile: float) -> float:
    if len(values) == 1:
        return values[0]
    position = (len(values) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return values[lower]
    weight = position - lower
    return values[lower] * (1 - weight) + values[upper] * weight


def _outer_thirds(values: list[float]) -> tuple[list[float], list[float]]:
    size = max(1, len(values) // 3)
    return values[:size], values[-size:]


def _linear_regression_r2(values: list[float]) -> float:
    count = len(values)
    if count < 2:
        return 0.0
    x_mean = (count - 1) / 2
    y_mean = statistics.fmean(values)
    ss_x = sum((index - x_mean) ** 2 for index in range(count))
    ss_y = sum((value - y_mean) ** 2 for value in values)
    if ss_x <= 0 or ss_y <= 0:
        return 0.0
    covariance = sum((index - x_mean) * (value - y_mean) for index, value in enumerate(values))
    return _clamp((covariance * covariance) / (ss_x * ss_y))


def _spearman(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    ranks = _average_ranks(values)
    x_mean = (len(values) - 1) / 2
    y_mean = statistics.fmean(ranks)
    numerator = sum((index - x_mean) * (rank - y_mean) for index, rank in enumerate(ranks))
    denominator = math.sqrt(
        sum((index - x_mean) ** 2 for index in range(len(values)))
        * sum((rank - y_mean) ** 2 for rank in ranks)
    )
    return numerator / denominator if denominator > 0 else 0.0


def _average_ranks(values: list[float]) -> list[float]:
    ordered = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    index = 0
    while index < len(ordered):
        end = index + 1
        while end < len(ordered) and ordered[end][1] == ordered[index][1]:
            end += 1
        rank = (index + 1 + end) / 2
        for position in range(index, end):
            ranks[ordered[position][0]] = rank
        index = end
    return ranks


def _linear_score(value: float, low: float, high: float) -> float:
    if value <= low:
        return 0.0
    if value >= high:
        return 100.0
    return (value - low) / (high - low) * 100


def _inverse_linear_score(value: float, best: float, worst: float) -> float:
    return 100.0 - _linear_score(value, best, worst)


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _sign(value: float) -> int:
    return 1 if value > 0 else -1 if value < 0 else 0


def _round(value: float, digits: int = 2) -> float:
    return round(float(value), digits)


__all__ = [
    "DEFAULT_CLEAN_K_V2_CONFIG",
    "analyze_clean_k_v2",
    "resolve_clean_k_v2_config",
]
