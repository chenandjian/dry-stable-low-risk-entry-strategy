"""Strategy4 risk/reward evaluation."""
from __future__ import annotations

from strategy4.models import RiskRewardResult


def evaluate_risk_reward(
    *,
    current_close: float,
    support_price: float,
    target_price: float,
    config: dict,
    is_core_leader: bool,
) -> RiskRewardResult:
    if current_close <= 0 or support_price <= 0 or target_price <= current_close:
        return RiskRewardResult(False, reject_reasons=["INVALID_RISK_REWARD_INPUT"])

    stop_loss = support_price * 0.98
    risk_ratio = (current_close - stop_loss) / current_close
    reward = target_price - current_close
    risk = current_close - stop_loss
    rr = reward / risk if risk > 0 else 0.0

    max_risk = float(config.get("max_risk_ratio", 0.15))
    aggressive_max = float(config.get("aggressive_max_risk_ratio", 0.20))
    min_rr = float(config.get("core_leader_min_reward_risk_ratio", 1.8) if is_core_leader else config.get("min_reward_risk_ratio", 2.0))

    rejects: list[str] = []
    if risk_ratio > aggressive_max:
        rejects.append("RISK_RATIO_TOO_HIGH")
    elif risk_ratio > max_risk and not is_core_leader:
        rejects.append("RISK_RATIO_ABOVE_STANDARD")
    if rr < min_rr:
        rejects.append("REWARD_RISK_TOO_LOW")

    return RiskRewardResult(
        passed=not rejects,
        support_price=round(support_price, 4),
        stop_loss=round(stop_loss, 4),
        target_price=round(target_price, 4),
        risk_ratio=round(risk_ratio, 4),
        reward_risk_ratio=round(rr, 4),
        reject_reasons=rejects,
    )
