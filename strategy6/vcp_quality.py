"""Absolute VCP structure-quality scoring for Strategy6 observations."""
from __future__ import annotations

import math

from strategy6.models import Strategy6VcpObservation, Strategy6VcpQuality


MODEL_VERSION = "VCP_QUALITY_V1"


def evaluate_vcp_quality(
    rows: list[dict],
    observation: Strategy6VcpObservation,
) -> Strategy6VcpQuality:
    """Score existing VCP evidence without changing candidate eligibility."""
    contractions = list(observation.contractions or [])
    if len(contractions) < 2:
        return Strategy6VcpQuality()

    indexes = {
        str(row.get("date") or row.get("trade_date") or ""): index
        for index, row in enumerate(rows)
    }
    intervals: list[int] = []
    for item in contractions:
        peak_index = indexes.get(str(item.get("peak_date") or ""))
        low_index = indexes.get(str(item.get("low_date") or ""))
        if peak_index is None or low_index is None or low_index <= peak_index:
            return Strategy6VcpQuality(
                warnings=["VCP_QUALITY_DATE_MAPPING_FAILED"],
                model_version=MODEL_VERSION,
            )
        intervals.append(low_index - peak_index)

    amplitudes = [_positive_float(item.get("amplitude")) for item in contractions]
    lows = [_positive_float(item.get("low_close")) for item in contractions]
    peaks = [_positive_float(item.get("peak_close")) for item in contractions]
    if any(value is None for value in (*amplitudes, *lows, *peaks)):
        return Strategy6VcpQuality(
            warnings=["VCP_QUALITY_EVIDENCE_INVALID"],
            model_version=MODEL_VERSION,
        )

    amplitude_values = [float(value) for value in amplitudes]
    low_values = [float(value) for value in lows]
    peak_values = [float(value) for value in peaks]
    range_ratios = [
        amplitude_values[index] / amplitude_values[index - 1]
        for index in range(1, len(amplitude_values))
    ]
    range_score = (
        _average_score(range_ratios, _score_range_ratio)
        + _score_last_amplitude(amplitude_values[-1])
        + _score_first_amplitude(amplitude_values[0])
    )

    warnings: list[str] = []
    volumes = [_positive_float(item.get("avg_volume")) for item in contractions]
    if any(value is None for value in volumes):
        volume_score = 0
        warnings.append("VCP_QUALITY_VOLUME_MISSING")
    else:
        volume_values = [float(value) for value in volumes]
        volume_ratios = [
            volume_values[index] / volume_values[index - 1]
            for index in range(1, len(volume_values))
        ]
        volume_score = (
            _average_score(volume_ratios, _score_volume_ratio)
            + _score_total_volume_ratio(volume_values[-1] / volume_values[0])
        )

    low_changes = [
        low_values[index] / low_values[index - 1] - 1
        for index in range(1, len(low_values))
    ]
    low_score = _average_score(low_changes, _score_low_change)

    first_peak_index = indexes[str(contractions[0].get("peak_date") or "")]
    last_low_index = indexes[str(contractions[-1].get("low_date") or "")]
    total_days = last_low_index - first_peak_index + 1
    one_day_count = sum(interval == 1 for interval in intervals)
    leg_score = 5 if one_day_count == 0 else 3 if one_day_count == 1 else 0
    time_score = _score_total_days(total_days) + leg_score

    peak_gap = abs(peak_values[-1] / peak_values[-2] - 1)
    pivot_score = _score_pivot_gap(peak_gap)
    contraction_score = _score_contraction_count(len(contractions))
    total = (
        contraction_score
        + range_score
        + volume_score
        + low_score
        + time_score
        + pivot_score
    )
    if amplitude_values[-1] < 0.01 and intervals[-1] == 1:
        warnings.append("VCP_MICRO_CONTRACTION_NOISE")
        total = min(total, 79)

    reasons = _quality_reasons(
        contraction_score=contraction_score,
        range_score=range_score,
        volume_score=volume_score,
        low_score=low_score,
        time_score=time_score,
        pivot_score=pivot_score,
    )
    return Strategy6VcpQuality(
        scored=True,
        score=total,
        grade=_grade_for_score(total),
        contraction_score=contraction_score,
        range_score=range_score,
        volume_score=volume_score,
        low_score=low_score,
        time_score=time_score,
        pivot_score=pivot_score,
        reasons=reasons,
        warnings=warnings,
        model_version=MODEL_VERSION,
    )


def _positive_float(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def _average_score(values: list[float], scorer) -> int:
    if not values:
        return 0
    return _round_half_up(sum(scorer(value) for value in values) / len(values))


def _round_half_up(value: float) -> int:
    return math.floor(value + 0.5)


def _score_contraction_count(count: int) -> int:
    if count >= 4:
        return 20
    if count == 3:
        return 17
    if count == 2:
        return 12
    return 0


def _score_range_ratio(ratio: float) -> int:
    return _bucket(ratio, ((0.35, 12), (0.50, 10), (0.65, 8), (0.80, 5), (0.90, 2)))


def _score_last_amplitude(amplitude: float) -> int:
    return _bucket(amplitude, ((0.03, 8), (0.05, 6), (0.08, 4), (0.10, 2)))


def _score_first_amplitude(amplitude: float) -> int:
    if 0.08 <= amplitude <= 0.25:
        return 5
    if amplitude <= 0.35 and amplitude > 0.25:
        return 3
    if amplitude <= 0.45 and amplitude > 0.35:
        return 1
    return 0


def _score_volume_ratio(ratio: float) -> int:
    return _bucket(ratio, ((0.50, 15), (0.65, 12), (0.75, 9), (0.85, 6), (0.90, 3)))


def _score_total_volume_ratio(ratio: float) -> int:
    return _bucket(ratio, ((0.35, 10), (0.50, 8), (0.65, 6), (0.80, 3), (0.90, 1)))


def _score_low_change(change: float) -> int:
    if change >= 0.02:
        return 15
    if change >= 0:
        return 13
    if change >= -0.01:
        return 10
    if change >= -0.02:
        return 6
    if change >= -0.03:
        return 2
    return 0


def _score_total_days(days: int) -> int:
    if 12 <= days <= 45:
        return 5
    if 8 <= days <= 55:
        return 3
    return 1


def _score_pivot_gap(gap: float) -> int:
    return _bucket(gap, ((0.03, 5), (0.05, 3), (0.08, 1)))


def _bucket(value: float, levels: tuple[tuple[float, int], ...]) -> int:
    for upper, score in levels:
        if value <= upper:
            return score
    return 0


def _grade_for_score(score: int) -> str:
    if score >= 90:
        return "TOP"
    if score >= 80:
        return "HIGH"
    if score >= 70:
        return "GOOD"
    if score >= 60:
        return "NORMAL"
    return "WEAK"


def _quality_reasons(**scores: int) -> list[str]:
    thresholds = {
        "contraction_score": (17, "VCP_QUALITY_MULTI_CONTRACTION"),
        "range_score": (20, "VCP_QUALITY_RANGE_TIGHT"),
        "volume_score": (20, "VCP_QUALITY_VOLUME_DRY"),
        "low_score": (13, "VCP_QUALITY_LOW_STABLE"),
        "time_score": (8, "VCP_QUALITY_TIME_COMPACT"),
        "pivot_score": (3, "VCP_QUALITY_PIVOT_CLEAR"),
    }
    return [
        reason
        for field, (minimum, reason) in thresholds.items()
        if scores[field] >= minimum
    ]
