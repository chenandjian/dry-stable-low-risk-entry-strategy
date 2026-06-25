"""策略3健康回踩过滤与评分。"""
from strategy3.models import Strategy3Indicators


def evaluate_pullback(
    ind: Strategy3Indicators,
    data: list[dict],
    config: dict,
) -> tuple[list[str], int, list[str]]:
    rejects: list[str] = []
    reasons: list[str] = []
    if ind.pullback_pct < config["min_pullback_from_high"]:
        rejects.append("PULLBACK_TOO_SHALLOW")
    if ind.pullback_pct > config["max_pullback_from_high"]:
        rejects.append("PULLBACK_TOO_DEEP")
    if ind.range_5 > config["max_recent_range_5"]:
        rejects.append("RECENT_RANGE_TOO_WIDE")
    if _has_heavy_volume_drop(data):
        rejects.append("HEAVY_VOLUME_DROP")
    if len(data) >= 2 and float(data[-1]["close"]) < ind.ma60 and float(data[-2]["close"]) < ind.ma60:
        rejects.append("MA60_BREAKDOWN")

    score = 0
    if 0.10 <= ind.pullback_pct <= 0.22:
        score += 8
        reasons.append("ideal_pullback_depth")
    elif 0.08 <= ind.pullback_pct <= 0.30:
        score += 4
        reasons.append("acceptable_pullback_depth")
    if ind.current_close >= ind.ma60:
        score += 5
        reasons.append("above_ma60")
    if ind.ma20 > 0 and abs(ind.current_close / ind.ma20 - 1) <= 0.05:
        score += 4
        reasons.append("near_ma20")
    if not _has_heavy_volume_drop(data[-10:]):
        score += 4
        reasons.append("no_recent_heavy_drop")
    if not _lows_breaking_down(data[-5:]):
        score += 4
        reasons.append("lows_not_breaking_down")
    return rejects, min(score, 25), reasons


def _has_heavy_volume_drop(data: list[dict]) -> bool:
    if len(data) < 2:
        return False
    v20 = sum(float(row["volume"]) for row in data[-20:]) / min(len(data), 20)
    for prev, curr in zip(data[-6:-1], data[-5:]):
        prev_close = float(prev["close"])
        change = float(curr["close"]) / prev_close - 1 if prev_close > 0 else 0.0
        if change <= -0.05 and float(curr["volume"]) > v20:
            return True
    return False


def _lows_breaking_down(data: list[dict]) -> bool:
    if len(data) < 3:
        return False
    lows = [float(row["low"]) for row in data]
    return lows[-1] < lows[-2] < lows[-3]

