"""Final dry-stable low-risk entry decision.

Decision types (7 states):
  REJECT          "不建议买入"   — hard block
  WAIT_VOLUME     "等量能萎缩"   — volume not dry enough
  WAIT_STABLE     "等价格企稳"   — price not stable enough
  WAIT_ENTRY      "等回调入场"   — price above entry zone
  WAIT_RR         "等盈亏比改善" — RR1 too low
  WATCH_BREAKOUT  "突破确认"     — near pivot, waiting for breakout
  BUY_LOW         "可低吸"       — all conditions met
"""

from dataclasses import dataclass, field


@dataclass
class DryStableDecision:
    verdict: str = "不建议买入"
    verdict_key: str = "REJECT"
    summary: str = ""
    in_low_buy_zone: bool = False
    near_pivot: bool = False
    is_chasing: bool = False
    reasons: list[str] = field(default_factory=list)
    invalid_conditions: list[str] = field(default_factory=list)
    positive_factors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    reject_reasons: list[str] = field(default_factory=list)


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

# Ordered by severity — used for frontend display priority
VERDICT_LABELS = {
    "REJECT": "不建议买入",
    "WAIT_VOLUME": "等量能萎缩",
    "WAIT_STABLE": "等价格企稳",
    "WAIT_ENTRY": "等回调入场",
    "WAIT_RR": "等盈亏比改善",
    "WATCH_BREAKOUT": "突破确认",
    "BUY_LOW": "可低吸",
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
    extra_warnings: list[str] | None = None,
    extra_positive: list[str] | None = None,
    extra_reject: list[str] | None = None,
) -> DryStableDecision:
    """Apply the hard rules from the dry-stable strategy document.

    Args:
        decision_cfg: 来自 config.yaml 的 decision 段。
        extra_warnings/positive/reject: 从量干/价稳/风报模块汇总的附加信息。
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
    d.positive_factors = list(extra_positive or [])
    d.warnings = list(extra_warnings or [])
    d.reject_reasons = list(extra_reject or [])

    current = key_prices.current_price
    low = key_prices.entry_zone_low
    high = key_prices.entry_zone_high
    pivot = key_prices.pivot

    d.in_low_buy_zone = low > 0 and high > 0 and low <= current <= high
    d.near_pivot = pivot > 0 and current <= pivot * (1 + chase_pct / 100)
    d.is_chasing = pivot > 0 and current > pivot * (1 + chase_pct / 100)

    def _reject(key, reason, inv=None):
        d.verdict_key = key
        d.verdict = VERDICT_LABELS[key]
        d.summary = reason
        if inv: d.invalid_conditions = inv
        d.reject_reasons.append(reason)
        return d

    if invalid_conditions:
        return _reject("REJECT", invalid_conditions[0], invalid_conditions)
    if market_status == "较差":
        return _reject("REJECT", "大盘环境较差")

    if pattern_score < min_pattern:
        return _reject("REJECT", "形态不成熟")

    if volume_dry_score < min_vd:
        d.verdict_key = "WAIT_VOLUME"
        d.verdict = VERDICT_LABELS["WAIT_VOLUME"]
        d.summary = f"量干评分{volume_dry_score}<{min_vd}，等待成交量进一步萎缩。"
        d.reasons = [f"量干{volume_dry_score}分未达{min_vd}分门槛", "继续等待量能进一步萎缩"]
        return d

    if price_stable_score < min_ps:
        d.verdict_key = "WAIT_STABLE"
        d.verdict = VERDICT_LABELS["WAIT_STABLE"]
        d.summary = f"价稳评分{price_stable_score}<{min_ps}，等待价格进一步企稳。"
        d.reasons = [f"价稳{price_stable_score}分未达{min_ps}分门槛", "继续等待价格收窄企稳"]
        return d

    if risk_reward.risk_percent > max_risk:
        return _reject("REJECT", f"止损空间{risk_reward.risk_percent:.1f}%超过{max_risk:.0f}%上限")

    if risk_reward.rr1 < min_rr1:
        d.verdict_key = "WAIT_RR"
        d.verdict = VERDICT_LABELS["WAIT_RR"]
        d.summary = f"盈亏比RR1={risk_reward.rr1}<{min_rr1}，等待更好入场点。"
        d.reasons = [f"第一目标盈亏比{risk_reward.rr1}未达{min_rr1}", "等待价格回调改善盈亏比"]
        return d

    if d.is_chasing:
        return _reject("REJECT", f"当前价高于Pivot超过{chase_pct}%，已远离低风险买点")

    # --- BUY_LOW ---
    if (
        pattern_score >= lb_pattern
        and volume_dry_score >= lb_vd
        and price_stable_score >= lb_ps
        and risk_reward.risk_percent <= lb_max_risk
        and risk_reward.rr1 >= min_rr1
        and d.in_low_buy_zone
    ):
        d.verdict_key = "BUY_LOW"
        d.verdict = VERDICT_LABELS["BUY_LOW"]
        d.summary = "量干价稳，当前价处于低吸区间内，止损空间和盈亏比合格。"
        d.reasons = [
            "形态评分达到成熟标准",
            "量干评分达到低吸标准",
            "价稳评分达到低吸标准",
            "当前价靠近柄部/支撑低吸区间",
            f"止损空间不超过{lb_max_risk:.0f}%且第一目标盈亏比不低于{min_rr1}:1",
        ]
        return d

    # --- WATCH_BREAKOUT ---
    if (
        pattern_score >= lb_pattern
        and volume_dry_score >= min_vd
        and price_stable_score >= min_ps
        and d.near_pivot
    ):
        d.verdict_key = "WATCH_BREAKOUT"
        d.verdict = VERDICT_LABELS["WATCH_BREAKOUT"]
        d.summary = "形态有效但当前低吸位置不够理想，等待放量突破或回踩确认。"
        d.reasons = [
            "形态评分达到成熟标准",
            "量价状态达到观察标准",
            f"当前价未远离Pivot超过{chase_pct}%",
        ]
        if not d.in_low_buy_zone:
            d.reasons.append("当前价不在理想低吸区间内")
        return d

    # --- WAIT_ENTRY (default fallback when checks pass but not in zone) ---
    if not d.in_low_buy_zone:
        d.verdict_key = "WAIT_ENTRY"
        d.verdict = VERDICT_LABELS["WAIT_ENTRY"]
        d.summary = "条件基本满足但当前价不在低吸区间内，等待回调。"
        d.reasons = ["硬性条件通过", "等待价格回调到入场区间"]
        return d

    d.verdict_key = "WATCH_BREAKOUT"
    d.verdict = VERDICT_LABELS["WATCH_BREAKOUT"]
    d.summary = "条件尚未同时满足，继续等待。"
    d.reasons = ["核心硬性条件未破坏，但低风险买点尚未出现"]
    return d
