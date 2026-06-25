"""策略3风险收益计算。"""
from strategy3.models import Strategy3Indicators, Strategy3Risk


def compute_strategy3_risk(
    data: list[dict],
    ind: Strategy3Indicators,
    config: dict,
) -> tuple[Strategy3Risk, list[str], int, list[str]]:
    support_window = data[-int(config["support_lookback_days"]):]
    support_low = min(float(row["low"]) for row in support_window)
    pullback_window = data[-int(config["pullback_lookback_days"]):]
    recent_high_index = max(
        range(len(pullback_window)),
        key=lambda idx: float(pullback_window[idx]["high"]),
    )
    pullback_after_high = pullback_window[recent_high_index:]
    pullback_low = min(float(row["low"]) for row in pullback_after_high)
    support_price = min(pullback_low, ind.ma20, support_low)
    stop_loss = support_price * 0.98
    risk_ratio = (ind.current_close - stop_loss) / ind.current_close if ind.current_close > 0 else 1.0
    high_target = ind.recent_high
    target_1 = high_target * 1.03 if high_target > 0 and (high_target - ind.current_close) / high_target < 0.02 else high_target
    rr1 = (target_1 - ind.current_close) / (ind.current_close - stop_loss) if ind.current_close > stop_loss else 0.0

    risk = Strategy3Risk(
        support_price=support_price,
        stop_loss=stop_loss,
        target_1=target_1,
        risk_ratio=risk_ratio,
        rr1=rr1,
    )

    rejects: list[str] = []
    if risk_ratio > config["max_risk_ratio"]:
        rejects.append("RISK_RATIO_TOO_HIGH")
    if target_1 <= ind.current_close or rr1 < 1.5:
        rejects.append("RR_TOO_LOW")

    score = 0
    reasons: list[str] = []
    if risk_ratio <= 0.08:
        score += 4
        reasons.append("risk_ratio<=8%")
    if risk_ratio <= 0.05:
        score += 3
        reasons.append("risk_ratio<=5%")
    if rr1 >= 1.5:
        score += 4
        reasons.append("rr1>=1.5")
    if rr1 >= 2:
        score += 2
        reasons.append("rr1>=2")
    if ind.current_close >= support_price:
        score += 2
        reasons.append("above_support")
    return risk, rejects, min(score, 15), reasons
