"""Strategy6 six-dimension scoring."""
from __future__ import annotations

from strategy6.models import (
    Strategy6DryTail,
    Strategy6Indicators,
    Strategy6Pattern,
    Strategy6Phase,
    Strategy6Score,
    Strategy6Start,
    Strategy6Support,
    Strategy6TradePlan,
)


def score_strategy6(
    ind: Strategy6Indicators,
    start: Strategy6Start,
    phase: Strategy6Phase,
    pattern: Strategy6Pattern,
    support: Strategy6Support,
    dry_tail: Strategy6DryTail,
    trade_plan: Strategy6TradePlan,
    config: dict,
) -> Strategy6Score:
    strong = _strong_start_score(start)
    pattern_score = 20 if not config["pattern_filter_enabled"] else min(
        20, pattern.pattern_score + (1 if phase.valid and pattern.pattern_score < 20 else 0)
    )
    support_score = min(20, support.support_cluster_score + (2 if support.support_test_count >= 2 else 1 if support.support_test_count else 0))
    tail_score = min(20, dry_tail.dry_stable_score)
    objective_rr_score = _rr_score(trade_plan.objective_rr_2)
    relative_strength_risk_score = _relative_strength_risk_score(ind)
    total = min(100, strong + pattern_score + support_score + tail_score + objective_rr_score + relative_strength_risk_score)
    reasons = [
        f"strong={strong}",
        f"pattern={pattern_score}",
        f"support={support_score}",
        f"tail={tail_score}",
        f"objective_rr={objective_rr_score}",
        f"rs_risk={relative_strength_risk_score}",
    ]
    return Strategy6Score(
        strong_start_score=strong,
        pattern_score_component=pattern_score,
        support_score=support_score,
        tail_score=tail_score,
        dry_stable_score=tail_score,
        objective_rr_score=objective_rr_score,
        risk_reward_score=objective_rr_score,
        relative_strength_risk_score=relative_strength_risk_score,
        risk_control_score=relative_strength_risk_score,
        total_score=total,
        score_reasons=reasons,
    )


def _strong_start_score(start: Strategy6Start) -> int:
    grade = {"S": 8, "A": 6, "B": 4}.get(start.start_grade, 0)
    volume = 4 if start.start_day_volume_ratio >= 2.5 else 3 if start.start_day_volume_ratio >= 2.0 else 1
    close_position = 2 if start.start_day_close_position >= 0.75 else 1 if start.start_day_close_position >= 0.65 else 0
    attention = 3 if start.start_day_self_amount_percentile >= 0.90 else 0
    high = 3 if start.high_trigger == "new_120d_high" else 2 if start.high_trigger else 0
    return min(20, grade + volume + close_position + attention + high)


def _rr_score(objective_rr_2: float) -> int:
    if objective_rr_2 >= 3.0:
        return 10
    if objective_rr_2 >= 2.5:
        return 8
    if objective_rr_2 >= 2.0:
        return 6
    if objective_rr_2 >= 1.5:
        return 3
    return 0


def _relative_strength_risk_score(ind: Strategy6Indicators) -> int:
    rs = 0
    if ind.relative_strength_20_observed:
        if ind.relative_strength_20 >= 0.20:
            rs = 5
        elif ind.relative_strength_20 >= 0.15:
            rs = 4
        elif ind.relative_strength_20 >= 0.10:
            rs = 3
    risk = 5
    if ind.has_big_down_volume:
        risk -= 5
    if "UPPER_SHADOW_PRESSURE" in ind.warn_tags:
        risk -= 2
    if "PRESSURE_NEAR_HIGH" in ind.warn_tags:
        risk -= 1
    if ind.market_filter_enabled and ind.market_filter_mode == "score_only" and ind.market_status in {"MARKET_WEAK", "MARKET_RISK"}:
        risk -= 2
    return max(0, rs + risk)
