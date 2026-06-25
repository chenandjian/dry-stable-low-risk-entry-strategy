"""策略3缩量企稳过滤与评分。"""
from strategy3.models import Strategy3Indicators


def evaluate_volume_stability(
    ind: Strategy3Indicators,
    data: list[dict],
    config: dict,
) -> tuple[list[str], int, list[str]]:
    rejects: list[str] = []
    reasons: list[str] = []
    if ind.volume_ratio_5_20 > 1.20 and ind.return_3 < 0.03:
        rejects.append("VOLUME_NOT_STABLE")
    if ind.close_range_5 > 0.08:
        rejects.append("CLOSE_RANGE_TOO_WIDE")
    if _three_black_crows(data):
        rejects.append("RECENT_CONTINUOUS_DROP")

    score = 0
    if ind.volume_ratio_5_20 <= config["volume_shrink_ratio"]:
        score += 5
        reasons.append("volume_ratio_5_20<=shrink_ratio")
    if ind.volume_ratio_5_20 <= 0.70:
        score += 5
        reasons.append("volume_extremely_shrink")
    if ind.close_range_5 <= 0.05:
        score += 4
        reasons.append("close_range_tight")
    if not _lows_declining(data[-5:]):
        score += 3
        reasons.append("lows_stable")
    if ind.down_day_volume_ratio == 0 or ind.down_day_volume_ratio < 1.0:
        score += 3
        reasons.append("down_day_volume_below_v20")
    return rejects, min(score, 20), reasons


def _three_black_crows(data: list[dict]) -> bool:
    if len(data) < 4:
        return False
    last3 = data[-3:]
    all_down = all(float(row["close"]) < float(row["open"]) for row in last3)
    base = float(data[-4]["close"])
    total_drop = float(data[-1]["close"]) / base - 1 if base > 0 else 0.0
    return all_down and total_drop < -0.06


def _lows_declining(data: list[dict]) -> bool:
    if len(data) < 3:
        return False
    lows = [float(row["low"]) for row in data]
    return lows[-1] < lows[-2] < lows[-3]

