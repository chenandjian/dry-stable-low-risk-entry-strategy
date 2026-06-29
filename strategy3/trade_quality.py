"""策略3交易质量过滤层。"""
from __future__ import annotations

from strategy3.models import Strategy3Indicators, Strategy3Risk, Strategy3TradeQuality


def evaluate_trade_quality(
    data: list[dict],
    ind: Strategy3Indicators,
    risk: Strategy3Risk,
    config: dict,
) -> Strategy3TradeQuality:
    """Evaluate whether a strategy3 signal is actually tradeable."""
    trigger_reasons: list[str] = []
    risk_warnings: list[str] = []
    invalid_conditions: list[str] = []

    support = risk.tactical_support or risk.support_price
    key_support = risk.key_support or ind.key_support
    stop_loss = risk.tactical_stop_loss or risk.stop_loss
    target_price = risk.target_1
    current = ind.current_close

    support_distance = _distance_pct(current, support)
    key_support_distance = _distance_pct(current, key_support)
    target_room = (target_price - current) / current if current > 0 and target_price > 0 else 0.0
    estimated_rr = _estimated_rr(current, stop_loss, target_price)
    effective_risk_ratio = (
        (current - stop_loss) / current
        if current > stop_loss and current > 0
        else risk.tactical_risk_ratio or risk.risk_ratio
    )

    volume_score, volume_reasons = _score_volume_dry(ind, config)
    price_score, price_reasons = _score_price_stability(ind, config)
    cannot_fall_score, cannot_fall_reasons = _score_cannot_fall(ind, risk, config)
    balance_score, balance_reasons = _score_balance_powerless(ind, config)
    trigger_reasons.extend(volume_reasons)
    trigger_reasons.extend(price_reasons)
    trigger_reasons.extend(cannot_fall_reasons)
    trigger_reasons.extend(balance_reasons)

    low_absorb_support_distance = float(config.get("trade_low_absorb_support_distance", 0.04))
    watch_support_distance = float(config.get("trade_watch_support_distance", 0.06))
    low_absorb_max_risk = float(config.get("trade_low_absorb_max_risk_ratio", 0.06))
    max_risk_ratio = float(config.get("max_risk_ratio", 0.08))
    min_rr = float(config.get("trade_min_rr", 1.5))
    low_absorb_min_rr = float(config.get("trade_low_absorb_min_rr", 2.0))
    min_target_room = float(config.get("trade_min_target_room", 0.06))
    low_absorb_min_target_room = float(config.get("trade_low_absorb_min_target_room", 0.10))

    if volume_score < 15:
        risk_warnings.append("risk:volume_not_dry_enough")
    if price_score < 15:
        risk_warnings.append("risk:price_stability_not_enough")
    if cannot_fall_score < 14:
        risk_warnings.append("risk:cannot_fall_not_confirmed")
    if balance_score < 12:
        risk_warnings.append("risk:balance_powerless_not_confirmed")
    if support_distance > low_absorb_support_distance:
        risk_warnings.append("risk:support_too_far_for_low_absorb")
    else:
        trigger_reasons.append("support:near_tactical_support")
    if effective_risk_ratio > low_absorb_max_risk:
        risk_warnings.append("risk:stop_space_not_small_enough")
    if target_room < low_absorb_min_target_room:
        risk_warnings.append("risk:target_room_not_enough_for_low_absorb")
    if estimated_rr < low_absorb_min_rr:
        risk_warnings.append("risk:rr_not_enough_for_low_absorb")

    invalid_conditions.extend(_hard_invalid_conditions(ind, risk))
    if price_score < 12 or ind.range_5 > 0.08 or ind.close_range_5 > 0.06:
        invalid_conditions.append("PRICE_NOT_STABLE")
    if ind.atr_ratio_5_20 >= float(config.get("dry_atr_expand_reject_ratio", 1.20)):
        invalid_conditions.append("DOWNSIDE_VOLATILITY_EXPANDING")
    if effective_risk_ratio > max_risk_ratio:
        invalid_conditions.append("RISK_RATIO_TOO_HIGH")
    if target_price <= current or estimated_rr < min_rr:
        invalid_conditions.append("RR_TOO_LOW")
    if target_room < min_target_room:
        invalid_conditions.append("TARGET_ROOM_TOO_SMALL")

    trade_quality_score = min(
        100,
        volume_score + price_score + cannot_fall_score + balance_score
        + _risk_quality_score(effective_risk_ratio, estimated_rr, target_room, support_distance),
    )

    trade_state = _determine_trade_state(
        invalid_conditions=invalid_conditions,
        volume_score=volume_score,
        price_score=price_score,
        cannot_fall_score=cannot_fall_score,
        balance_score=balance_score,
        support_distance=support_distance,
        effective_risk_ratio=effective_risk_ratio,
        target_room=target_room,
        estimated_rr=estimated_rr,
        low_absorb_support_distance=low_absorb_support_distance,
        watch_support_distance=watch_support_distance,
        low_absorb_max_risk=low_absorb_max_risk,
        max_risk_ratio=max_risk_ratio,
        low_absorb_min_target_room=low_absorb_min_target_room,
        low_absorb_min_rr=low_absorb_min_rr,
        min_rr=min_rr,
    )

    return Strategy3TradeQuality(
        trade_quality_score=trade_quality_score,
        volume_dry_score=volume_score,
        price_stability_score=price_score,
        cannot_fall_score=cannot_fall_score,
        balance_powerless_score=balance_score,
        support_distance_pct=support_distance,
        key_support_distance_pct=key_support_distance,
        target_price=target_price,
        target_room_pct=target_room,
        estimated_rr=estimated_rr,
        trade_state=trade_state,
        trade_state_label=_state_label(trade_state),
        trigger_reasons=_dedupe(trigger_reasons),
        risk_warnings=_dedupe(risk_warnings),
        invalid_conditions=_dedupe(invalid_conditions),
        reject_reasons=_dedupe(invalid_conditions),
    )


def _score_volume_dry(ind: Strategy3Indicators, config: dict) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    shrink_ratio = float(config.get("volume_shrink_ratio", 0.70))
    dry_ratio = float(config.get("dry_volume_ratio", 0.60))
    extreme_ratio = float(config.get("dry_extreme_volume_ratio", 0.50))
    if 0 < ind.volume_ratio_5_20 <= shrink_ratio:
        score += 4
        reasons.append("volume:dry")
    if 0 < ind.volume_ratio_5_20 <= dry_ratio:
        score += 4
        reasons.append("volume:strong_dry")
    if 0 < ind.volume_ratio_5_20 <= extreme_ratio:
        score += 3
        reasons.append("volume:extreme_dry")
    if 0 < ind.v3 < ind.v5 < ind.v10 < ind.v20:
        score += 4
        reasons.append("volume:v3_v5_v10_v20_contracting")
    if 0 < ind.volume_percentile_60 <= 0.20:
        score += 3
        reasons.append("volume:low_volume_percentile")
    if ind.down_volume_ratio_5 <= float(config.get("dry_down_volume_ratio_max", 0.60)) and not ind.has_big_down_volume:
        score += 2
        reasons.append("volume:down_volume_exhausted")
    return min(score, 20), reasons


def _score_price_stability(ind: Strategy3Indicators, config: dict) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    if 0 < ind.range_5 <= 0.05:
        score += 4
        reasons.append("price:range_5_tight")
    if 0 < ind.close_range_5 <= float(config.get("dry_balance_close_range_tight", 0.03)):
        score += 4
        reasons.append("price:close_range_tight")
    if 0 < ind.atr_ratio_5_20 <= float(config.get("dry_atr_contract_ratio", 0.75)):
        score += 4
        reasons.append("price:atr_contracted")
    if (
        ind.max_up_5 <= float(config.get("dry_balance_max_up_5", 0.03))
        and ind.max_down_5 >= float(config.get("dry_balance_max_down_5", -0.03))
    ):
        score += 3
        reasons.append("price:max_daily_move_balanced")
    if ind.range_compression_ok:
        score += 3
        reasons.append("price:range_compression_sequence")
    if (
        float(config.get("dry_balance_close_position_min", 0.35))
        <= ind.avg_close_position_5
        <= float(config.get("dry_balance_close_position_max", 0.65))
    ):
        score += 2
        reasons.append("price:close_position_balanced")
    if score >= 15:
        reasons.append("price:stable")
    return min(score, 20), reasons


def _score_cannot_fall(
    ind: Strategy3Indicators,
    risk: Strategy3Risk,
    config: dict,
) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    if ind.no_new_low:
        score += 4
        reasons.append("cannot_fall:no_new_low")
    if ind.new_low_count_5 == 0:
        score += 3
        reasons.append("cannot_fall:no_new_low_count")
    if (risk.support_status or ind.support_status) in {"VALID", "TESTING"}:
        score += 3
        reasons.append("cannot_fall:support_valid")
    if ind.bear_body_shrink:
        score += 2
        reasons.append("cannot_fall:bear_body_shrink")
    if ind.down_return_contracting:
        score += 2
        reasons.append("cannot_fall:down_return_contracting")
    if ind.lower_shadow_count >= int(config.get("dry_lower_shadow_min_count", 2)):
        score += 2
        reasons.append("cannot_fall:lower_shadow_support")
    if not ind.has_big_down_volume:
        score += 2
        reasons.append("cannot_fall:no_heavy_down_volume")
    return min(score, 20), reasons


def _score_balance_powerless(ind: Strategy3Indicators, config: dict) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    if ind.direction_efficiency_5 <= float(config.get("dry_balance_direction_efficiency_threshold", 0.35)):
        score += 4
        reasons.append("balance:direction_efficiency_low")
    if ind.direction_efficiency_5 <= float(config.get("dry_balance_extreme_direction_efficiency_threshold", 0.25)):
        score += 2
        reasons.append("balance:direction_efficiency_extreme")
    if 0 < ind.avg_abs_return_5 <= 0.015:
        score += 4
        reasons.append("balance:avg_abs_return_tight")
    if (
        ind.max_up_5 <= float(config.get("dry_balance_max_up_5", 0.03))
        and ind.max_down_5 >= float(config.get("dry_balance_max_down_5", -0.03))
    ):
        score += 3
        reasons.append("balance:max_daily_move_balanced")
    if ind.range_compression_ok:
        score += 3
        reasons.append("balance:range_compression")
    if 0 < ind.volume_ratio_5_20 <= float(config.get("volume_shrink_ratio", 0.70)):
        score += 2
        reasons.append("balance:low_volume")
    if 0 < ind.atr_ratio_5_20 <= float(config.get("dry_atr_contract_ratio", 0.75)):
        score += 2
        reasons.append("balance:atr_contracted")
    return min(score, 20), reasons


def _hard_invalid_conditions(ind: Strategy3Indicators, risk: Strategy3Risk) -> list[str]:
    invalid: list[str] = []
    support_status = risk.support_status or ind.support_status
    break_status = risk.break_status or ind.break_status
    if ind.has_big_down_volume:
        invalid.append("VOLUME_BREAKDOWN")
    if support_status == "FAILED" or break_status == "EFFECTIVE_BREAK":
        invalid.append("KEY_SUPPORT_FAILED")
    elif support_status == "BROKEN":
        invalid.append("KEY_SUPPORT_BROKEN")
    if ind.new_low_count_5 >= 2 or not ind.no_new_low:
        invalid.append("CONTINUOUS_NEW_LOW")
    if ind.bear_body_expanding:
        invalid.append("BEAR_BODY_EXPANDING")
    return invalid


def _risk_quality_score(
    risk_ratio: float,
    estimated_rr: float,
    target_room: float,
    support_distance: float,
) -> int:
    score = 0
    if support_distance <= 0.04:
        score += 5
    elif support_distance <= 0.06:
        score += 3
    if risk_ratio <= 0.06:
        score += 5
    elif risk_ratio <= 0.08:
        score += 3
    if estimated_rr >= 2.0:
        score += 5
    elif estimated_rr >= 1.5:
        score += 3
    if target_room >= 0.10:
        score += 5
    elif target_room >= 0.06:
        score += 3
    return score


def _determine_trade_state(
    *,
    invalid_conditions: list[str],
    volume_score: int,
    price_score: int,
    cannot_fall_score: int,
    balance_score: int,
    support_distance: float,
    effective_risk_ratio: float,
    target_room: float,
    estimated_rr: float,
    low_absorb_support_distance: float,
    watch_support_distance: float,
    low_absorb_max_risk: float,
    max_risk_ratio: float,
    low_absorb_min_target_room: float,
    low_absorb_min_rr: float,
    min_rr: float,
) -> str:
    if invalid_conditions:
        return "AVOID"
    low_absorb_ok = (
        volume_score >= 15
        and price_score >= 15
        and cannot_fall_score >= 14
        and balance_score >= 12
        and support_distance <= low_absorb_support_distance
        and effective_risk_ratio <= low_absorb_max_risk
        and target_room >= low_absorb_min_target_room
        and estimated_rr >= low_absorb_min_rr
    )
    if low_absorb_ok:
        return "LOW_ABSORB"
    if (
        volume_score >= 12
        and price_score >= 12
        and cannot_fall_score >= 10
        and support_distance > low_absorb_support_distance
        and effective_risk_ratio <= max_risk_ratio
        and estimated_rr >= min_rr
    ):
        return "WAIT_BREAKOUT"
    if (
        (volume_score >= 10 or price_score >= 10)
        and effective_risk_ratio <= max_risk_ratio
        and estimated_rr >= min_rr
        and support_distance <= max(watch_support_distance, low_absorb_support_distance)
    ):
        return "WATCH"
    return "WATCH"


def _state_label(state: str) -> str:
    return {
        "LOW_ABSORB": "低吸",
        "WATCH": "观察",
        "WAIT_BREAKOUT": "等待突破",
        "AVOID": "回避",
    }.get(state, "")


def _distance_pct(current: float, support: float) -> float:
    if current <= 0 or support <= 0:
        return 0.0
    return max(0.0, (current - support) / current)


def _estimated_rr(current: float, stop_loss: float, target: float) -> float:
    if current <= 0 or stop_loss <= 0 or target <= current or current <= stop_loss:
        return 0.0
    return (target - current) / (current - stop_loss)


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
