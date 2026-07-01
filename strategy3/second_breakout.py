"""策略3二次转强过滤与评分。"""
from strategy3.models import Strategy3Indicators


def evaluate_second_breakout(
    ind: Strategy3Indicators,
    data: list[dict],
    config: dict,
) -> tuple[list[str], int, list[str]]:
    rejects: list[str] = []
    reasons: list[str] = []
    ma5_prev = _ma(data[:-1], 5)
    if ind.current_close < ind.ma5 and ind.ma5 < ma5_prev:
        rejects.append("MA5_NOT_RECOVERED")
    if ind.return_3 >= config["max_recent_surge_3"]:
        rejects.append("RECENT_OVERHEATED")
    high20 = max(float(row["high"]) for row in data[-20:])
    if high20 > 0 and (high20 - ind.current_close) / high20 < 0.01 and ind.return_3 > 0.07:
        rejects.append("CHASE_NEAR_HIGH")

    score = 0
    if ind.current_close >= ind.ma5:
        score += 3
        reasons.append("close_above_ma5")
    if ind.current_close >= ind.ma10:
        score += 3
        reasons.append("close_above_ma10")
    if sum(1 for row in data[-3:] if float(row["close"]) > float(row["open"])) >= 2:
        score += 3
        reasons.append("two_positive_days_in_3")
    closes = [float(row["close"]) for row in data[-5:]]
    if closes and ind.current_close >= (min(closes) + max(closes)) / 2:
        score += 3
        reasons.append("close_in_upper_half_5")
    volume_today = float(data[-1]["volume"])
    if volume_today > ind.v5 and volume_today <= 1.8 * ind.v20:
        score += 3
        reasons.append("moderate_volume_expansion")
    return rejects, min(score, 15), reasons


def _ma(data: list[dict], days: int) -> float:
    if len(data) < days:
        return 0.0
    return sum(float(row["close"]) for row in data[-days:]) / days

