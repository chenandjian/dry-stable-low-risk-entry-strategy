"""Strategy6 scoring."""
from __future__ import annotations

from strategy6.models import (
    Strategy6DryTail,
    Strategy6Indicators,
    Strategy6Score,
    Strategy6Start,
    Strategy6Support,
    Strategy6TradePlan,
)


def score_strategy6(
    ind: Strategy6Indicators,
    start: Strategy6Start,
    support: Strategy6Support,
    dry_tail: Strategy6DryTail,
    trade_plan: Strategy6TradePlan,
) -> Strategy6Score:
    strong = _strong_start_score(start)
    support_score = support.support_score
    dry = dry_tail.dry_stable_score
    rr = _rr_score(trade_plan.risk_reward_ratio_2)
    risk_control = _risk_control_score(ind, start, trade_plan)
    total = min(100, strong + support_score + dry + rr + risk_control)
    reasons = [
        f"strong={strong}",
        f"support={support_score}",
        f"dry={dry}",
        f"rr={rr}",
        f"risk={risk_control}",
    ]
    return Strategy6Score(
        strong_start_score=strong,
        support_score=support_score,
        dry_stable_score=dry,
        risk_reward_score=rr,
        risk_control_score=risk_control,
        total_score=total,
        score_reasons=reasons,
    )


def _strong_start_score(start: Strategy6Start) -> int:
    if start.start_grade == "S":
        base = 22
    elif start.start_grade == "A":
        base = 17
    elif start.start_grade == "B":
        base = 12
    else:
        return 0
    if start.start_type in {"VOLUME_LIMIT_UP", "ONE_WORD_LIMIT_UP"}:
        base += 3
    elif start.start_type == "LOW_VOLUME_LIMIT_UP":
        base += 2
    elif start.start_type == "NORMAL_STRONG_BREAKOUT":
        base += 1
    return min(25, base)


def _rr_score(rr2: float) -> int:
    if rr2 >= 3.0:
        return 15
    if rr2 >= 2.5:
        return 12
    if rr2 >= 2.0:
        return 10
    if rr2 >= 1.5:
        return 6
    return 0


def _risk_control_score(ind: Strategy6Indicators, start: Strategy6Start, trade_plan: Strategy6TradePlan) -> int:
    score = 10
    if ind.daily_return <= -0.07:
        score -= 5
    if ind.range_5 > 0.22:
        score -= 3
    if ind.range_10 > 0.45:
        score -= 3
    if ind.pullback_from_20d_high < -0.30:
        score -= 3
    if start.start_type == "ONE_WORD_LIMIT_UP" and trade_plan.risk_reward_ratio_2 < 2.0:
        score -= 5
    if ind.volume_ratio_5_20 > 0.90:
        score -= 5
    return max(0, score)

