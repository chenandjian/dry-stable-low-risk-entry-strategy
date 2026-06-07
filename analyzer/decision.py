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


def make_dry_stable_decision(
    pattern_score: int,
    volume_dry_score: int,
    price_stable_score: int,
    key_prices,
    risk_reward,
    invalid_conditions: list[str] | None = None,
    market_status: str = "一般",
    max_risk_percent: float = 8,
) -> DryStableDecision:
    """Apply the hard rules from the dry-stable strategy document.

    Args:
        max_risk_percent: 止损空间上限（%），超过此值直接 reject。默认 8。
    """
    d = DryStableDecision()

    current = key_prices.current_price
    low = key_prices.entry_zone_low
    high = key_prices.entry_zone_high
    pivot = key_prices.pivot

    d.in_low_buy_zone = low > 0 and high > 0 and low <= current <= high
    d.near_pivot = pivot > 0 and current <= pivot * 1.05
    d.is_chasing = pivot > 0 and current > pivot * 1.05

    if invalid_conditions:
        return _block(d, invalid_conditions[0], invalid_conditions)
    if market_status == "较差":
        return _block(d, "大盘环境较差")

    if pattern_score < 8:
        return _block(d, "形态不成熟")
    if volume_dry_score < 6:
        return _block(d, "量能未干")
    if price_stable_score < 6:
        return _block(d, "价格未稳")
    if risk_reward.risk_percent > max_risk_percent:
        return _block(d, f"止损空间超过{max_risk_percent:.0f}%")
    if risk_reward.rr1 < 2:
        return _block(d, "第一目标盈亏比低于2:1")
    if d.is_chasing:
        return _block(d, "当前价高于Pivot超过5%，已远离低风险买点")

    if (
        pattern_score >= 13
        and volume_dry_score >= 7
        and price_stable_score >= 7
        and risk_reward.risk_percent <= 6
        and risk_reward.rr1 >= 2
        and d.in_low_buy_zone
    ):
        d.verdict = "可低吸"
        d.summary = "量干价稳，当前价处于低吸区间内，止损空间和盈亏比合格。"
        d.reasons = [
            "形态评分达到成熟标准",
            "量干评分达到低吸标准",
            "价稳评分达到低吸标准",
            "当前价靠近柄部/支撑低吸区间",
            "止损空间不超过6%且第一目标盈亏比不低于2:1",
        ]
        return d

    if (
        pattern_score >= 13
        and volume_dry_score >= 6
        and price_stable_score >= 6
        and d.near_pivot
    ):
        d.verdict = "突破确认"
        d.summary = "形态有效但当前低吸位置不够理想，等待放量突破或回踩确认。"
        d.reasons = [
            "形态评分达到成熟标准",
            "量价状态达到观察标准",
            "当前价未远离Pivot超过5%",
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
