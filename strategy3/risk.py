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
    structural_support = pullback_low
    structural_stop_loss = structural_support * 0.98
    structural_risk_ratio = (
        (ind.current_close - structural_stop_loss) / ind.current_close
        if ind.current_close > 0 else 1.0
    )
    if ind.key_support > 0:
        tactical_support = ind.key_support
        support_quality = ",".join(ind.support_sources) if ind.support_sources else "key_support"
        stop_buffer = float(config.get("support_stop_buffer_pct", 0.01))
        tactical_stop_loss = ind.key_support_zone_low * (1 - stop_buffer)
    else:
        tactical_support, support_quality = _select_tactical_support(
            ind.current_close,
            [
                ("pullback_low", pullback_low),
                ("support_low", support_low),
                ("ma20", ind.ma20),
                ("ma60", ind.ma60),
            ],
            fallback=structural_support,
        )
        tactical_stop_loss = tactical_support * 0.98
    tactical_risk_ratio = (
        (ind.current_close - tactical_stop_loss) / ind.current_close
        if ind.current_close > 0 else 1.0
    )
    high_target = ind.recent_high
    target_1 = high_target * 1.03 if high_target > 0 and (high_target - ind.current_close) / high_target < 0.02 else high_target
    tactical_rr1 = (
        (target_1 - ind.current_close) / (ind.current_close - tactical_stop_loss)
        if ind.current_close > tactical_stop_loss else 0.0
    )
    structural_rr1 = (
        (target_1 - ind.current_close) / (ind.current_close - structural_stop_loss)
        if ind.current_close > structural_stop_loss else 0.0
    )

    risk = Strategy3Risk(
        support_price=tactical_support,
        stop_loss=tactical_stop_loss,
        target_1=target_1,
        risk_ratio=tactical_risk_ratio,
        rr1=tactical_rr1,
        structural_support=structural_support,
        structural_stop_loss=structural_stop_loss,
        structural_risk_ratio=structural_risk_ratio,
        structural_rr1=structural_rr1,
        tactical_support=tactical_support,
        tactical_stop_loss=tactical_stop_loss,
        tactical_risk_ratio=tactical_risk_ratio,
        tactical_rr1=tactical_rr1,
        support_quality=support_quality,
        short_support=ind.short_support,
        short_support_zone_low=ind.short_support_zone_low,
        short_support_zone_high=ind.short_support_zone_high,
        key_support=ind.key_support or tactical_support,
        key_support_zone_low=ind.key_support_zone_low,
        key_support_zone_high=ind.key_support_zone_high,
        strong_support=ind.strong_support or structural_support,
        strong_support_zone_low=ind.strong_support_zone_low,
        strong_support_zone_high=ind.strong_support_zone_high,
        support_status=ind.support_status,
        break_status=ind.break_status,
        nearest_support_distance=ind.nearest_support_distance,
        support_sources=list(ind.support_sources),
    )

    rejects: list[str] = []
    if ind.support_status == "FAILED":
        rejects.append("KEY_SUPPORT_FAILED")
    elif ind.support_status == "BROKEN":
        rejects.append("KEY_SUPPORT_BROKEN")
    if tactical_risk_ratio > config["max_risk_ratio"]:
        rejects.append("RISK_RATIO_TOO_HIGH")
    if target_1 <= ind.current_close or tactical_rr1 < 1.5:
        rejects.append("RR_TOO_LOW")

    score = 0
    reasons: list[str] = []
    if tactical_risk_ratio <= 0.08:
        score += 4
        reasons.append("risk_ratio<=8%")
    if tactical_risk_ratio <= 0.05:
        score += 3
        reasons.append("risk_ratio<=5%")
    if tactical_rr1 >= 1.5:
        score += 4
        reasons.append("rr1>=1.5")
    if tactical_rr1 >= 2:
        score += 2
        reasons.append("rr1>=2")
    if ind.current_close >= tactical_support:
        score += 2
        reasons.append("above_support")
    if ind.support_status in {"VALID", "TESTING"}:
        score += 1
        reasons.append(f"support_status:{ind.support_status}")
    if support_quality:
        reasons.append(f"tactical_support:{support_quality}")
    return risk, rejects, min(score, 15), reasons


def _select_tactical_support(
    current_close: float,
    candidates: list[tuple[str, float]],
    *,
    fallback: float,
) -> tuple[float, str]:
    valid = [
        (name, float(value))
        for name, value in candidates
        if value and float(value) > 0 and float(value) < current_close
    ]
    if not valid:
        return fallback, "structural_fallback"

    valid.sort(key=lambda item: item[1], reverse=True)
    for name, value in valid:
        gap = (current_close - value) / current_close if current_close > 0 else 1.0
        if gap >= 0.01:
            return value, name
    return valid[0][1], f"{valid[0][0]}_tight"
