"""策略3评分聚合。"""
from strategy3.models import Strategy3Score


def build_strategy3_score(
    *,
    trend_score: int,
    pullback_score: int,
    volume_stability_score: int,
    second_breakout_score: int,
    risk_reward_score: int,
    score_reasons: list[str],
    config: dict,
) -> Strategy3Score:
    total = min(
        100,
        trend_score + pullback_score + volume_stability_score
        + second_breakout_score + risk_reward_score,
    )
    if total >= config["core_min_score"]:
        level = "核心候选"
    elif total >= config["candidate_min_score"]:
        level = "观察候选"
    elif total >= 65:
        level = "低优先级观察"
    else:
        level = "未入选"
    return Strategy3Score(
        trend_score=trend_score,
        pullback_score=pullback_score,
        volume_stability_score=volume_stability_score,
        second_breakout_score=second_breakout_score,
        risk_reward_score=risk_reward_score,
        total_score=total,
        level=level,
        score_reasons=score_reasons,
    )


def determine_status_reason(reject_reasons: list[str], total_score: int, config: dict) -> str | None:
    if reject_reasons:
        priority = [
            "RECENT_OVERHEATED",
            "CHASE_NEAR_HIGH",
            "DEEP_DRAWDOWN_FROM_HIGH",
            "PULLBACK_TOO_DEEP",
            "PULLBACK_TOO_SHALLOW",
            "RISK_RATIO_TOO_HIGH",
            "RR_TOO_LOW",
        ]
        for reason in priority:
            if reason in reject_reasons:
                return reason
        return reject_reasons[0]
    if total_score < config["candidate_min_score"]:
        return "SCORE_BELOW_THRESHOLD"
    return None
