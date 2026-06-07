# analyzer/risk_reward.py
"""Risk/Reward Calculator — 风险收益比 + 仓位建议。"""

from dataclasses import dataclass


@dataclass
class RiskRewardResult:
    risk_percent: float = 0.0
    reward_1: float = 0.0
    reward_2: float = 0.0
    rr1: float = 0.0
    rr2: float = 0.0
    risk_level: str = "高"
    position_advice: str = "0%"
    can_buy: bool = False


def calculate_risk_reward(key_prices, volume_dry_score: int = 0, price_stable_score: int = 0,
                          pattern_score: int = 0,
                          decision_cfg: dict | None = None) -> RiskRewardResult:
    """Calculate risk/reward ratio and position sizing advice.

    Args:
        decision_cfg: 来自 config.yaml 的 decision 段。
    """
    cfg = {**DEFAULT_RR_CFG, **(decision_cfg or {})}
    max_risk = float(cfg["max_risk_percent"])
    min_rr1 = float(cfg["min_rr1"])
    lb_pattern = int(cfg["low_buy_min_pattern_score"])
    lb_vd = int(cfg["low_buy_min_volume_dry"])
    lb_ps = int(cfg["low_buy_min_price_stable"])
    lb_max_risk = float(cfg["low_buy_max_risk_percent"])
    min_vd = int(cfg["min_volume_dry_score"])
    min_ps = int(cfg["min_price_stable_score"])

    r = RiskRewardResult()

    cp = key_prices.current_price
    sl = key_prices.stop_loss
    t1 = key_prices.target_1
    t2 = key_prices.target_2

    if cp <= 0 or sl <= 0:
        return r

    # Risk
    risk = cp - sl
    r.risk_percent = round(risk / cp * 100, 1)
    r.reward_1 = round(t1 - cp, 2)
    r.reward_2 = round(t2 - cp, 2)

    # Risk/Reward ratios
    if risk > 0:
        r.rr1 = round((t1 - cp) / risk, 1)
        r.rr2 = round((t2 - cp) / risk, 1)

    # Hard rules
    if r.risk_percent > max_risk:
        r.can_buy = False
        r.risk_level = "高风险"
        r.position_advice = "0%"
        return r

    if r.rr1 < min_rr1:
        r.can_buy = False
        r.risk_level = "高风险"
        r.position_advice = "0%"
        return r

    # Risk level determination
    all_good = (
        pattern_score >= lb_pattern
        and volume_dry_score >= lb_vd
        and price_stable_score >= lb_ps
        and r.risk_percent <= lb_max_risk
        and r.rr1 >= min_rr1
    )

    if all_good:
        r.risk_level = "低"
        r.can_buy = True
    elif volume_dry_score >= min_vd and price_stable_score >= min_ps and pattern_score >= lb_pattern:
        r.risk_level = "中"
        r.can_buy = False
    else:
        r.risk_level = "高"
        r.can_buy = False

    # Position sizing
    if r.risk_level == "低":
        if r.risk_percent <= 4:
            r.position_advice = "40%-50%"
        else:
            r.position_advice = "30%-40%"
    elif r.risk_level == "中":
        if r.risk_percent <= lb_max_risk:
            r.position_advice = "20%-30%"
        else:
            r.position_advice = "10%-20%"
    else:
        r.position_advice = "0%"

    return r


DEFAULT_RR_CFG = {
    "max_risk_percent": 8,
    "min_rr1": 2.0,
    "low_buy_min_pattern_score": 13,
    "low_buy_min_volume_dry": 7,
    "low_buy_min_price_stable": 7,
    "low_buy_max_risk_percent": 6,
    "min_volume_dry_score": 6,
    "min_price_stable_score": 6,
}
