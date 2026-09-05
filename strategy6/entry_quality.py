"""As-of entry timing and probability-adjusted RR diagnostics for Strategy6."""
from __future__ import annotations

from strategy6.models import (
    Strategy6EntryTiming,
    Strategy6Indicators,
    Strategy6ProbabilityAdjustedRR,
    Strategy6Support,
    Strategy6TradePlan,
)


def entry_quality_hard_filter_reasons(
    timing: Strategy6EntryTiming,
    probability_rr: Strategy6ProbabilityAdjustedRR,
    config: dict,
) -> list[str]:
    settings = config["entry_quality"]
    reasons = []
    if settings["entry_timing_enabled"] and timing.state == "INVALID":
        reasons.append("ENTRY_TIMING_INVALID")
    if (
        settings["probability_rr_enabled"]
        and probability_rr.reliable
        and probability_rr.probability_adjusted_r < settings["probability_min_watch_r"]
    ):
        threshold = str(settings["probability_min_watch_r"]).replace(".", "_")
        reasons.append(f"PROBABILITY_ADJUSTED_R_LT_{threshold}")
    return reasons


def entry_quality_blocks_tier(
    candidate_type: str,
    timing: Strategy6EntryTiming,
    probability_rr: Strategy6ProbabilityAdjustedRR,
    config: dict,
) -> bool:
    settings = config["entry_quality"]
    if candidate_type not in {"READY_CANDIDATE", "KEY_CANDIDATE"}:
        return False
    if settings["entry_timing_enabled"] and not timing.executable:
        return True
    if not settings["probability_rr_enabled"] or not probability_rr.reliable:
        return False
    threshold = (
        settings["probability_min_ready_r"]
        if candidate_type == "READY_CANDIDATE"
        else settings["probability_min_key_r"]
    )
    return probability_rr.probability_adjusted_r < threshold


def evaluate_entry_timing(
    rows: list[dict],
    ind: Strategy6Indicators,
    support: Strategy6Support,
    *,
    entry_archetype: str,
) -> Strategy6EntryTiming:
    """Classify current execution timing without changing the setup archetype."""
    if support.support_status == "SUPPORT_FAILED":
        return Strategy6EntryTiming(
            state="INVALID",
            risk_tags=["ENTRY_SUPPORT_FAILED"],
        )
    if ind.has_big_down_volume:
        return Strategy6EntryTiming(
            state="INVALID",
            risk_tags=["ENTRY_BIG_DOWN_VOLUME"],
        )
    support_floor = _support_floor(support)
    if support_floor > 0 and float(ind.current_price or 0.0) < support_floor:
        return Strategy6EntryTiming(
            state="INVALID",
            risk_tags=["ENTRY_CLOSE_BELOW_SUPPORT_FLOOR"],
        )
    if entry_archetype == "PIVOT_BREAKOUT":
        return Strategy6EntryTiming(
            state="BREAKOUT_CONFIRMED",
            executable=True,
            reasons=["ENTRY_EXISTING_BREAKOUT_CONFIRMED"],
        )
    if entry_archetype == "FAILED_BREAKOUT_RECLAIM":
        return Strategy6EntryTiming(
            state="RECLAIM_CONFIRMED",
            executable=True,
            reasons=["ENTRY_EXISTING_RECLAIM_CONFIRMED"],
        )
    if entry_archetype == "WAIT_BREAKOUT":
        return Strategy6EntryTiming(
            state="WAITING_BREAKOUT",
            reasons=["ENTRY_WAITING_FOR_PIVOT_BREAKOUT"],
        )
    if entry_archetype != "SUPPORT_PULLBACK" or len(rows) < 5:
        return Strategy6EntryTiming()

    recent = rows[-5:]
    latest = recent[-1]
    latest_low = float(latest.get("low") or 0.0)
    prior_low = min(float(row.get("low") or 0.0) for row in recent[:-1])
    latest_close = float(latest.get("close") or ind.current_price or 0.0)
    prior_close = float(recent[-2].get("close") or 0.0)
    no_new_low = latest_low >= prior_low
    close_turning_up = latest_close > prior_close
    close_position = _close_position(latest, ind.current_close_position)
    close_position_good = close_position >= 0.55
    volume_contracting = _pullback_volume_contracting(rows)
    reclaim_floor = _support_floor(support)
    support_reclaimed = reclaim_floor > 0 and latest_close >= reclaim_floor

    evidence = [
        (no_new_low, "ENTRY_NO_NEW_LOW"),
        (close_turning_up, "ENTRY_CLOSE_TURNING_UP"),
        (close_position_good, "ENTRY_CLOSE_POSITION_RECOVERED"),
        (volume_contracting, "ENTRY_PULLBACK_VOLUME_CONTRACTING"),
        (support_reclaimed, "ENTRY_SUPPORT_RECLAIMED"),
    ]
    reasons = [reason for passed, reason in evidence if passed]
    risks = []
    if not no_new_low:
        risks.append("ENTRY_LATEST_NEW_LOW")
    if not close_position_good:
        risks.append("ENTRY_WEAK_CLOSE_POSITION")
    if not volume_contracting:
        risks.append("ENTRY_PULLBACK_VOLUME_NOT_CONTRACTING")
    if not support_reclaimed:
        risks.append("ENTRY_SUPPORT_NOT_RECLAIMED")
    confirmed = no_new_low and support_reclaimed and len(reasons) >= 3
    return Strategy6EntryTiming(
        state="SUPPORT_CONFIRMED" if confirmed else "SUPPORT_FORMING",
        executable=confirmed,
        evidence_count=len(reasons),
        reasons=reasons,
        risk_tags=risks,
    )


def evaluate_probability_adjusted_rr(
    rows: list[dict],
    ind: Strategy6Indicators,
    trade_plan: Strategy6TradePlan,
    *,
    lookback_days: int,
    horizon_days: int,
    minimum_samples: int,
) -> Strategy6ProbabilityAdjustedRR:
    """Estimate target reachability from completed pre-signal historical paths."""
    atr = float(ind.atr14 or 0.0)
    risk = float(trade_plan.risk_amount or 0.0)
    reward_1 = float(trade_plan.reward_amount_1 or 0.0)
    reward_2 = float(trade_plan.reward_amount_2 or 0.0)
    if min(atr, risk, reward_1, reward_2) <= 0 or horizon_days < 1:
        return Strategy6ProbabilityAdjustedRR(
            status="INVALID_TRADE_PLAN",
            lookback_days=lookback_days,
            horizon_days=horizon_days,
            reasons=["PROBABILITY_RR_INVALID_TRADE_PLAN"],
        )

    risk_atr = risk / atr
    target_1_atr = reward_1 / atr
    target_2_atr = reward_2 / atr
    final_anchor = len(rows) - horizon_days - 1
    first_anchor = max(14, final_anchor - lookback_days + 1)
    anchors = list(range(first_anchor, final_anchor + 1)) if final_anchor >= first_anchor else []
    target_1_hits = 0
    target_2_hits = 0
    sample_count = 0
    for anchor in anchors:
        anchor_atr = _atr_at(rows, anchor, 14)
        anchor_close = float(rows[anchor].get("close") or 0.0)
        if anchor_atr <= 0 or anchor_close <= 0:
            continue
        sample_count += 1
        future = rows[anchor + 1:anchor + horizon_days + 1]
        stop = anchor_close - risk_atr * anchor_atr
        target_1 = anchor_close + target_1_atr * anchor_atr
        target_2 = anchor_close + target_2_atr * anchor_atr
        if _target_hit_before_stop(future, stop, target_1):
            target_1_hits += 1
        if _target_hit_before_stop(future, stop, target_2):
            target_2_hits += 1

    reliable = sample_count >= minimum_samples
    probability_1 = target_1_hits / sample_count if sample_count else 0.0
    probability_2 = target_2_hits / sample_count if sample_count else 0.0
    probability_2 = min(probability_1, probability_2)
    adjusted_r = (
        probability_2 * float(trade_plan.objective_rr_2 or 0.0)
        + (probability_1 - probability_2) * float(trade_plan.objective_rr_1 or 0.0)
        - (1.0 - probability_1)
    )
    return Strategy6ProbabilityAdjustedRR(
        status="RELIABLE" if reliable else "INSUFFICIENT_SAMPLE",
        reliable=reliable,
        sample_count=sample_count,
        lookback_days=lookback_days,
        horizon_days=horizon_days,
        risk_atr=round(risk_atr, 6),
        target_1_atr=round(target_1_atr, 6),
        target_2_atr=round(target_2_atr, 6),
        target_1_hit_probability=round(probability_1, 6),
        target_2_hit_probability=round(probability_2, 6),
        probability_adjusted_r=round(adjusted_r, 6),
        reasons=[
            "PROBABILITY_RR_ASOF_HISTORY",
            "PROBABILITY_RR_STOP_FIRST",
            *([] if reliable else ["PROBABILITY_RR_INSUFFICIENT_SAMPLE"]),
        ],
    )


def _pullback_volume_contracting(rows: list[dict]) -> bool:
    recent = rows[-3:]
    baseline = rows[max(0, len(rows) - 23):-3]
    if not recent or not baseline:
        return False
    recent_avg = sum(float(row.get("volume") or 0.0) for row in recent) / len(recent)
    baseline_avg = sum(float(row.get("volume") or 0.0) for row in baseline) / len(baseline)
    return baseline_avg > 0 and recent_avg <= baseline_avg * 0.90


def _support_floor(support: Strategy6Support) -> float:
    floors = [
        float(value)
        for value in (support.tactical_support_price, support.support_zone_low)
        if float(value or 0.0) > 0
    ]
    return min(floors) if floors else 0.0


def _close_position(row: dict, fallback: float) -> float:
    high = float(row.get("high") or 0.0)
    low = float(row.get("low") or 0.0)
    close = float(row.get("close") or 0.0)
    if high > low:
        return (close - low) / (high - low)
    return float(fallback or 0.0)


def _atr_at(rows: list[dict], index: int, period: int) -> float:
    start = max(0, index - period + 1)
    true_ranges = []
    for current in range(start, index + 1):
        high = float(rows[current].get("high") or 0.0)
        low = float(rows[current].get("low") or 0.0)
        previous_close = (
            float(rows[current - 1].get("close") or 0.0)
            if current > 0 else float(rows[current].get("close") or 0.0)
        )
        true_ranges.append(max(high - low, abs(high - previous_close), abs(low - previous_close)))
    return sum(true_ranges) / len(true_ranges) if true_ranges else 0.0


def _target_hit_before_stop(future: list[dict], stop: float, target: float) -> bool:
    for row in future:
        if float(row.get("low") or 0.0) <= stop:
            return False
        if float(row.get("high") or 0.0) >= target:
            return True
    return False
