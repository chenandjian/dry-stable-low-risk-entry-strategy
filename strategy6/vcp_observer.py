"""Independent as-of VCP structure observer for Strategy6."""
from __future__ import annotations

from strategy6.models import Strategy6VcpObservation
from strategy6.pattern import _best_vcp_chain, _swing_contractions
from strategy6.strong_start import find_historical_start_anchor


def evaluate_vcp_observation(
    rows: list[dict],
    config: dict,
    *,
    code: str = "",
) -> Strategy6VcpObservation:
    """Rebuild the latest observable VCP lifecycle from rows known as of today."""
    if not bool(config.get("vcp_observer_enabled", True)):
        return Strategy6VcpObservation()

    lookback = int(config["vcp_observer_lookback_days"])
    window = rows[-lookback:]
    if len(window) < 10:
        return Strategy6VcpObservation(risk_tags=["VCP_DATA_INSUFFICIENT"])

    chain = _best_vcp_chain(_swing_contractions(window), config)
    if len(chain) < 2:
        return Strategy6VcpObservation()

    last = chain[-1]
    pivot = float(last["peak_close"])
    structure_low = float(last["low_close"])
    current_close = float(window[-1]["close"])
    distance_to_pivot = current_close / pivot - 1 if pivot > 0 else 0.0
    evidence = _serialize_chain(window, chain)
    window_start = len(rows) - len(window)
    anchor = find_historical_start_anchor(
        rows,
        config,
        code,
        end_index=window_start + chain[0]["peak_index"],
    )
    reasons = [
        "VCP_ORIGIN_STRONG_START",
        "VCP_SWING_CONTRACTIONS",
        "VCP_RANGE_CONTRACTING",
        "VCP_VOLUME_CONTRACTING",
        "VCP_LOW_NOT_FALLING",
    ]

    result = Strategy6VcpObservation(
        eligible=True,
        lifecycle_status="VCP_FORMING",
        origin_start_date=anchor.start_date if anchor else "",
        pattern_start_date=str(window[chain[0]["peak_index"]].get("date") or ""),
        pattern_end_date=str(window[last["low_index"]].get("date") or ""),
        contraction_count=len(chain),
        contractions=evidence,
        pivot_price=round(pivot, 4),
        structure_low=round(structure_low, 4),
        distance_to_pivot_pct=round(distance_to_pivot, 6),
        reasons=reasons,
    )
    if anchor is None:
        result.eligible = False
        result.lifecycle_status = "VCP_NONE"
        result.reasons.remove("VCP_ORIGIN_STRONG_START")
        result.risk_tags.append("VCP_ORIGIN_START_MISSING")
        return result
    result.risk_tags.extend(anchor.failure_reasons)

    structure_broken = any(
        float(row.get("close") or 0.0) < structure_low
        for row in window[last["low_index"] + 1:]
    )
    if structure_broken:
        result.eligible = False
        result.lifecycle_status = "VCP_INVALID"
        result.invalidation_reason = "VCP_STRUCTURE_LOW_BROKEN"
        result.risk_tags.append("VCP_STRUCTURE_LOW_BROKEN")
        return result

    breakout_offset = _find_confirmed_breakout(
        window,
        start_index=last["low_index"] + 1,
        pivot=pivot,
    )
    if breakout_offset is None:
        proximity = float(config["pattern_pivot_proximity_pct"])
        if pivot > 0 and current_close >= pivot * (1 - proximity):
            result.lifecycle_status = "VCP_NEAR_PIVOT"
            result.reasons.append("VCP_NEAR_PIVOT")
        return result

    breakout_row = window[breakout_offset]
    result.breakout_date = str(breakout_row.get("date") or "")
    result.days_since_breakout = len(window) - 1 - breakout_offset
    volume_breakdown = _find_unrecovered_volume_breakdown(
        window,
        start_index=breakout_offset + 1,
        pivot=pivot,
        volume_ratio_threshold=float(config["big_down_volume_ratio"]),
    )
    if volume_breakdown is not None:
        result.eligible = False
        result.lifecycle_status = "VCP_INVALID"
        result.invalidation_reason = "VCP_VOLUME_BREAKDOWN_UNRECOVERED"
        result.risk_tags.append("VCP_VOLUME_BREAKDOWN_UNRECOVERED")
        return result

    retention = int(config["vcp_observer_breakout_retention_days"])
    if result.days_since_breakout > retention:
        result.eligible = False
        result.lifecycle_status = "VCP_NONE"
        result.risk_tags.append("VCP_OBSERVATION_EXPIRED")
        return result

    if current_close < pivot:
        result.risk_tags.append("VCP_PIVOT_LOST")
        proximity = float(config["pattern_pivot_proximity_pct"])
        if current_close >= pivot * (1 - proximity):
            result.lifecycle_status = "VCP_NEAR_PIVOT"
            result.reasons.append("VCP_NEAR_PIVOT")
        return result
    if distance_to_pivot > float(config["vcp_observer_extension_pct"]):
        result.lifecycle_status = "VCP_EXTENDED"
        result.risk_tags.append("VCP_PRICE_EXTENDED")
    elif result.days_since_breakout == 0:
        result.lifecycle_status = "VCP_BREAKOUT_CONFIRMED"
        result.reasons.append("VCP_BREAKOUT_CONFIRMED")
    else:
        result.lifecycle_status = "VCP_POST_BREAKOUT"
        result.reasons.append("VCP_POST_BREAKOUT")
    return result


def apply_vcp_base_filters(
    observation: Strategy6VcpObservation,
    reject_reasons: list[str],
) -> Strategy6VcpObservation:
    """Remove observation eligibility when data or liquidity is not trustworthy."""
    if not observation.eligible:
        return observation
    exact_blockers = {
        "MA_CALC_FAILED",
        "AVG60D_LT_MIN",
        "AVG30D_LT_MIN",
        "AVG10D_LT_MIN",
        "AVG10D_LT_AVG30D_RATIO",
        "LATEST_TRADE_SUSPENDED",
        "LATEST_TRADE_NO_TRADE",
    }
    blockers = [
        reason for reason in reject_reasons
        if reason in exact_blockers or reason.startswith("TRADING_DAYS_LT_")
    ]
    if not blockers:
        return observation
    observation.eligible = False
    observation.lifecycle_status = "VCP_NONE"
    observation.risk_tags = list(dict.fromkeys([
        *observation.risk_tags,
        "VCP_BASE_FILTER_FAILED",
        *blockers,
    ]))
    return observation


def _find_confirmed_breakout(
    rows: list[dict],
    *,
    start_index: int,
    pivot: float,
) -> int | None:
    for index in range(max(1, start_index), len(rows)):
        row = rows[index]
        close = float(row["close"])
        if close <= pivot:
            continue
        previous_close = float(rows[index - 1]["close"])
        daily_return = close / previous_close - 1 if previous_close > 0 else 0.0
        volume_ratio = _volume_ratio_against_prior(rows, index)
        if daily_return >= 0.05 or volume_ratio >= 1.20:
            return index
    return None


def _find_unrecovered_volume_breakdown(
    rows: list[dict],
    *,
    start_index: int,
    pivot: float,
    volume_ratio_threshold: float,
) -> int | None:
    recovery_days = 3
    for index in range(max(1, start_index), len(rows)):
        close = float(rows[index]["close"])
        previous_close = float(rows[index - 1]["close"])
        if close >= pivot or close >= previous_close:
            continue
        if _volume_ratio_against_prior(rows, index) < volume_ratio_threshold:
            continue
        grace_end = index + recovery_days
        if grace_end >= len(rows):
            continue
        if all(float(row["close"]) < pivot for row in rows[index + 1:grace_end + 1]):
            return index
    return None


def _volume_ratio_against_prior(rows: list[dict], index: int) -> float:
    baseline_start = max(0, index - 20)
    baseline = [float(item.get("volume") or 0.0) for item in rows[baseline_start:index]]
    positive = [volume for volume in baseline if volume > 0]
    average_volume = sum(positive) / len(positive) if positive else 0.0
    return float(rows[index].get("volume") or 0.0) / average_volume if average_volume > 0 else 0.0


def _serialize_chain(rows: list[dict], chain: list[dict]) -> list[dict]:
    result: list[dict] = []
    for index, item in enumerate(chain):
        previous = chain[index - 1] if index else None
        result.append({
            "peak_date": str(rows[item["peak_index"]].get("date") or ""),
            "low_date": str(rows[item["low_index"]].get("date") or ""),
            "peak_close": round(float(item["peak_close"]), 4),
            "low_close": round(float(item["low_close"]), 4),
            "amplitude": round(float(item["amplitude"]), 6),
            "avg_volume": round(float(item["avg_volume"]), 4),
            "range_ratio_to_previous": round(
                float(item["amplitude"]) / float(previous["amplitude"]), 6,
            ) if previous and float(previous["amplitude"]) > 0 else None,
            "volume_ratio_to_previous": round(
                float(item["avg_volume"]) / float(previous["avg_volume"]), 6,
            ) if previous and float(previous["avg_volume"]) > 0 else None,
        })
    return result
