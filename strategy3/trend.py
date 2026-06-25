"""策略3强势趋势过滤与评分。"""
from strategy3.models import Strategy3Indicators


def evaluate_trend(ind: Strategy3Indicators, config: dict) -> tuple[list[str], int, list[str]]:
    rejects: list[str] = []
    reasons: list[str] = []
    if ind.current_close < ind.ma60 and ind.ma20 < ind.ma60:
        rejects.append("BELOW_MA60_AND_WEAK_TREND")
    if ind.drawdown_from_high_120 > 0.35:
        rejects.append("DEEP_DRAWDOWN_FROM_HIGH")
    if ind.relative_strength_60 < config["min_relative_strength_60"]:
        rejects.append("RELATIVE_STRENGTH_WEAK")
    if ind.ma60_slope_20 < -0.03:
        rejects.append("MA60_SLOPE_WEAK")

    score = 0
    if ind.current_close >= ind.ma20 >= ind.ma60:
        score += 5
        reasons.append("close>=ma20>=ma60")
    if ind.current_close >= ind.ma60:
        score += 5
        reasons.append("close>=ma60")
    if ind.ma60_slope_20 > 0:
        score += 5
        reasons.append("ma60_slope_positive")
    if ind.relative_strength_60 >= config["min_relative_strength_60"]:
        score += 5
        reasons.append("relative_strength_ok")
    if ind.return_60 >= 0.10 and ind.drawdown_from_high_120 <= 0.25:
        score += 5
        reasons.append("return60_and_drawdown_ok")
    return rejects, min(score, 25), reasons

