"""Dry-stable low-risk entry analysis pipeline."""

from analyzer.decision import make_dry_stable_decision
from analyzer.invalid_rules import find_invalid_conditions
from analyzer.key_prices import calculate_key_prices
from analyzer.market_env import assess_market_environment
from analyzer.pattern_score import score_pattern
from analyzer.price_stable import score_price_stable
from analyzer.risk_reward import calculate_risk_reward
from analyzer.volume_dry import score_volume_dry


def analyze_dry_stable(result, data: list[dict], market_data: list[dict] | None = None,
                       config: dict | None = None) -> dict:
    """Run the full dry-stable analysis chain for a detected pattern.

    Args:
        config: 可选配置字典，支持 decision.max_risk_percent（默认 8）。
    """
    decision_cfg = (config or {}).get("decision", {})
    vd_cfg = (config or {}).get("volume_dry", {})
    ps_cfg = (config or {}).get("price_stable", {})

    vol_dry = score_volume_dry(data, config=vd_cfg)
    price_stable = score_price_stable(data, config=ps_cfg,
                                       handle_low=getattr(result, 'handle_low_price', 0))
    pattern = score_pattern(result, data)
    key_pattern_type = "vcp" if pattern.vcp_score > pattern.cup_handle_score else "cup_handle"
    key_prices = calculate_key_prices(result, data, pattern_type=key_pattern_type)
    rr = calculate_risk_reward(
        key_prices,
        volume_dry_score=vol_dry.total_score,
        price_stable_score=price_stable.total_score,
        pattern_score=pattern.total_score,
        decision_cfg=decision_cfg,
        data=data,
    )
    invalid_conditions = find_invalid_conditions(data, key_prices, result)
    market_env = assess_market_environment(market_data)

    # Aggregate warnings / positive / reject from sub-modules
    all_warnings = list(vol_dry.warnings) + list(price_stable.warnings) + list(rr.warnings)
    all_positive = list(price_stable.positive_factors)
    all_reject = list(vol_dry.reject_reasons) + list(price_stable.reject_reasons)

    decision = make_dry_stable_decision(
        pattern_score=pattern.total_score,
        volume_dry_score=vol_dry.total_score,
        price_stable_score=price_stable.total_score,
        key_prices=key_prices,
        risk_reward=rr,
        invalid_conditions=invalid_conditions,
        market_status=market_env.status,
        decision_cfg=decision_cfg,
        extra_warnings=all_warnings,
        extra_positive=all_positive,
        extra_reject=all_reject,
    )

    return {
        "decision": {
            "verdict": decision.verdict,
            "verdict_key": decision.verdict_key,
            "summary": decision.summary,
            "in_low_buy_zone": decision.in_low_buy_zone,
            "near_pivot": decision.near_pivot,
            "is_chasing": decision.is_chasing,
            "reasons": decision.reasons,
            "invalid_conditions": decision.invalid_conditions,
            "positive_factors": decision.positive_factors,
            "warnings": decision.warnings,
            "reject_reasons": decision.reject_reasons,
        },
        "volume_dry": {
            "score": vol_dry.total_score,
            "raw_score": vol_dry.raw_score,
            "verdict": vol_dry.verdict,
            "sub_scores": vol_dry.sub_scores,
            "details": vol_dry.details,
            "caps": vol_dry.caps,
            "warnings": vol_dry.warnings,
        },
        "price_stable": {
            "score": price_stable.total_score,
            "raw_score": price_stable.raw_score,
            "verdict": price_stable.verdict,
            "sub_scores": price_stable.sub_scores,
            "details": price_stable.details,
            "caps": price_stable.caps,
            "close_tightness_5d": price_stable.close_tightness_5d,
            "close_position_5d_avg": price_stable.close_position_5d_avg,
        },
        "pattern_score": {
            "score": pattern.total_score,
            "type": pattern.pattern_type,
            "cup_handle_score": pattern.cup_handle_score,
            "vcp_score": pattern.vcp_score,
            "key_pattern_type": key_pattern_type,
        },
        "key_prices": {
            "current_price": key_prices.current_price,
            "entry_zone_low": key_prices.entry_zone_low,
            "entry_zone_high": key_prices.entry_zone_high,
            "entry_zone": f"{key_prices.entry_zone_low} - {key_prices.entry_zone_high}",
            "pivot": key_prices.pivot,
            "stop_loss": key_prices.stop_loss,
            "target_1": key_prices.target_1,
            "target_2": key_prices.target_2,
        },
        "risk_reward": {
            "risk_percent": rr.risk_percent,
            "reward_1": rr.reward_1,
            "reward_2": rr.reward_2,
            "rr1": rr.rr1,
            "rr2": rr.rr2,
            "risk_level": rr.risk_level,
            "position_advice": rr.position_advice,
            "can_buy": rr.can_buy,
            "atr14_pct": rr.atr14_pct,
            "warnings": rr.warnings,
        },
        "market_environment": {
            "status": market_env.status,
            "position_advice": market_env.position_advice,
            "score": market_env.score,
            "reasons": market_env.reasons,
        },
        "trade_plan": {
            "can_act": decision.verdict in ("可低吸", "突破确认"),
            "buy_reasons": decision.reasons,
            "stop_reasons": [
                "止损价低于关键支撑或最后收缩低点",
                "跌破止损说明低风险结构失效",
            ],
            "target_reasons": [
                "第一目标按2R计算",
                "第二目标按3R或形态量度目标约束",
            ],
            "invalid_conditions": decision.invalid_conditions,
        },
    }
