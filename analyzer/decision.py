"""Final dry-stable low-risk entry decision.

This module is the single gate for the strategy's trading-style verdicts:
观察 / 可低吸 / 突破确认 / 不建议买入.
"""

from dataclasses import dataclass, field


@dataclass
class DryStableDecision:
    verdict: str = "不建议买入"
    summary: str = ""
    in_low_buy_zone: bool = False
    near_pivot: bool = False
    is_chasing: bool = False
    reasons: list[str] = field(default_factory=list)
    invalid_conditions: list[str] = field(default_factory=list)


DEFAULT_DECISION_CFG = {
    "min_pattern_score": 8,
    "min_volume_dry_score": 6,
    "min_price_stable_score": 6,
    "max_risk_percent": 8,
    "min_rr1": 2.0,
    "chase_threshold_pct": 5,
    "low_buy_min_pattern_score": 13,
    "low_buy_min_volume_dry": 7,
    "low_buy_min_price_stable": 7,
    "low_buy_max_risk_percent": 6,
}


def make_dry_stable_decision(
    pattern_score: int,
    volume_dry_score: int,
    price_stable_score: int,
    key_prices,
    risk_reward,
    invalid_conditions: list[str] | None = None,
    market_status: str = "一般",
    decision_cfg: dict | None = None,
) -> DryStableDecision:
    """Apply the hard rules from the dry-stable strategy document.

    Args:
        decision_cfg: 来自 config.yaml 的 decision 段，支持自定义所有阈值。
    """
    cfg = {**DEFAULT_DECISION_CFG, **(decision_cfg or {})}

    min_pattern = int(cfg["min_pattern_score"])
    min_vd = int(cfg["min_volume_dry_score"])
    min_ps = int(cfg["min_price_stable_score"])
    max_risk = float(cfg["max_risk_percent"])
    min_rr1 = float(cfg["min_rr1"])
    chase_pct = float(cfg["chase_threshold_pct"])
    lb_pattern = int(cfg["low_buy_min_pattern_score"])
    lb_vd = int(cfg["low_buy_min_volume_dry"])
    lb_ps = int(cfg["low_buy_min_price_stable"])
    lb_max_risk = float(cfg["low_buy_max_risk_percent"])

    d = DryStableDecision()

    current = key_prices.current_price
    low = key_prices.entry_zone_low
    high = key_prices.entry_zone_high
    pivot = key_prices.pivot

    d.in_low_buy_zone = low > 0 and high > 0 and low <= current <= high
    d.near_pivot = pivot > 0 and current <= pivot * (1 + chase_pct / 100)
    d.is_chasing = pivot > 0 and current > pivot * (1 + chase_pct / 100)

    if invalid_conditions:
        return _block(d, invalid_conditions[0], invalid_conditions)
    if market_status == "较差":
        return _block(d, "大盘环境较差")

    if pattern_score < min_pattern:
        return _block(d, "形态不成熟")
    if volume_dry_score < min_vd:
        return _block(d, "量能未干")
    if price_stable_score < min_ps:
        return _block(d, "价格未稳")
    if risk_reward.risk_percent > max_risk:
        return _block(d, f"止损空间超过{max_risk:.0f}%")
    if risk_reward.rr1 < min_rr1:
        return _block(d, f"第一目标盈亏比低于{min_rr1}:1")
    if d.is_chasing:
        return _block(d, f"当前价高于Pivot超过{chase_pct}%，已远离低风险买点")

    if (
        pattern_score >= lb_pattern
        and volume_dry_score >= lb_vd
        and price_stable_score >= lb_ps
        and risk_reward.risk_percent <= lb_max_risk
        and risk_reward.rr1 >= min_rr1
        and d.in_low_buy_zone
    ):
        d.verdict = "可低吸"
        d.summary = "量干价稳，当前价处于低吸区间内，止损空间和盈亏比合格。"
        d.reasons = [
            "形态评分达到成熟标准",
            "量干评分达到低吸标准",
            "价稳评分达到低吸标准",
            "当前价靠近柄部/支撑低吸区间",
            f"止损空间不超过{lb_max_risk:.0f}%且第一目标盈亏比不低于{min_rr1}:1",
        ]
        return d

    if (
        pattern_score >= lb_pattern
        and volume_dry_score >= min_vd
        and price_stable_score >= min_ps
        and d.near_pivot
    ):
        d.verdict = "突破确认"
        d.summary = "形态有效但当前低吸位置不够理想，等待放量突破或回踩确认。"
        d.reasons = [
            "形态评分达到成熟标准",
            "量价状态达到观察标准",
            f"当前价未远离Pivot超过{chase_pct}%",
        ]
        if not d.in_low_buy_zone:
            d.reasons.append("当前价不在理想低吸区间内")
        return d

    d.verdict = "观察"
    d.summary = "条件尚未同时满足，继续等待量能进一步萎缩、价格进一步收窄或回到低吸区间。"
    d.reasons = ["核心硬性条件未破坏，但低风险买点尚未出现"]
    return d


def _block(decision: DryStableDecision, reason: str, invalid_conditions: list[str] | None = None) -> DryStableDecision:
    decision.verdict = "不建议买入"
    decision.summary = f"不建议买入 - {reason}"
    decision.invalid_conditions = invalid_conditions or [reason]
    return decision
