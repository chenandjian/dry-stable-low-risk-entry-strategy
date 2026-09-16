"""Read-only EMA compression diagnosis; all percentage values are percent points."""
from math import isfinite
from statistics import mean, stdev


DEFAULTS = {
    "extreme": [0.30, 0.35, 0.35, 0.50, 0.10, 20, 1.50],
    "ultra": [0.20, 0.35, 0.25, 0.35, 0.06, 10, 1.00],
    "streak_threshold": 0.50,
    "score_tables": [
        [[.15, 20], [.20, 18], [.25, 16], [.30, 14], [.40, 10], [.50, 6]],
        [[.20, 25], [.25, 23], [.30, 20], [.35, 17], [.45, 12], [.55, 6]],
        [[.30, 15], [.35, 14], [.40, 12], [.50, 10], [.60, 6]],
        [[.04, 10], [.06, 9], [.08, 8], [.10, 6], [.15, 3]],
        [[5, 15], [10, 13], [15, 11], [20, 9], [30, 5]],
        [[.30, 10], [.50, 9], [.80, 8], [1, 7], [1.50, 4]],
        [[.70, 5], [.80, 4], [.90, 3], [1, 2]],
    ],
}


def evaluate_ema_compression(rows, config=None):
    result = {"status": "DATA_INSUFFICIENT", "score": None, "grade": None,
              "extreme": False, "ultraExtreme": False, "metrics": {},
              "reasons": [], "failReasons": [], "evaluationDate": ""}
    try:
        cfg = {**DEFAULTS, **(config or {})}
        for key in ("extreme", "ultra"):
            if len(cfg[key]) != 7 or any(isinstance(v, bool) or not isfinite(v) or v < 0 for v in cfg[key]):
                raise ValueError(key)
        if not isfinite(cfg['streak_threshold']) or cfg['streak_threshold'] < 0:
            raise ValueError('streak_threshold')
        if len(cfg['score_tables']) != 7:
            raise ValueError('score_tables')
        for table, cap in zip(cfg['score_tables'], [20, 25, 15, 10, 15, 10, 5]):
            if not table or any(len(pair) != 2 or not all(isfinite(v) for v in pair) or pair[0] < 0 or not 0 <= pair[1] <= cap for pair in table):
                raise ValueError('score_tables')
            if any(a[0] >= b[0] for a, b in zip(table, table[1:])):
                raise ValueError('score_tables order')
    except (TypeError, ValueError):
        result.update(status='CONFIG_INVALID', failReasons=['EMA缠绕诊断配置无效'])
        return result
    if not rows:
        return result
    result["evaluationDate"] = rows[-1]["date"]
    try:
        closes = [float(row["close"]) for row in rows]
        if any(not isfinite(value) or value <= 0 for value in closes):
            raise ValueError("invalid close")
        if any(str(a["date"]) >= str(b["date"]) for a, b in zip(rows, rows[1:])):
            raise ValueError("dates must be strictly increasing")
    except (KeyError, TypeError, ValueError):
        result["status"] = "DATA_INVALID"
        return result
    # 100 bars warm-up, then 120 prior complete five-bar samples plus today.
    if len(closes) < 225:
        result["failReasons"] = ["需要至少225根日线：EMA预热及此前120个有效历史样本"]
        return result
    emas = []
    for period in (5, 10, 20):
        values = [closes[0]]
        for close in closes[1:]:
            values.append(values[-1] + 2 / (period + 1) * (close - values[-1]))
        emas.append(values)
    spread = [(max(v) - min(v)) / mean(v) * 100 for v in zip(*emas)]
    history = [mean(spread[i-4:i+1]) for i in range(len(spread)-121, len(spread)-1)]
    now, avg3, avg5 = spread[-1], mean(spread[-3:]), mean(spread[-5:])
    maximum, deviation = max(spread[-5:]), stdev(spread[-5:])
    percentile = sum(value <= avg5 for value in history) / 120 * 100
    slope = (emas[2][-1] / emas[2][-6] - 1) * 100
    previous = mean(spread[-10:-5])
    change = avg5 / previous if previous > 0 else None
    streak = 0
    for value in reversed(spread[100:]):
        if value > cfg["streak_threshold"]:
            break
        streak += 1
    measured = [now, avg3, avg5, maximum, deviation, percentile, abs(slope)]
    extreme = all(v <= limit for v, limit in zip(measured, cfg["extreme"]))
    ultra = extreme and all(v <= limit for v, limit in zip(measured, cfg["ultra"]))
    score_values = [now, avg5, maximum, deviation, percentile, abs(slope), change]
    components = [next((points for limit, points in table if value <= limit), 0)
                  if value is not None else 0
                  for value, table in zip(score_values, cfg["score_tables"])]
    score = sum(components)
    labels = ["当前带宽", "3日平均带宽", "5日平均带宽", "5日最大带宽",
              "5日带宽标准差", "历史百分位", "EMA20五日变化绝对值"]
    result.update(status="ULTRA_EXTREME" if ultra else "EXTREME" if extreme else "NOT_CONFIRMED",
                  extreme=extreme, ultraExtreme=ultra, score=score,
                  grade=next((g for floor, g in [(90, "S"), (80, "A+"), (70, "A"), (60, "B"), (50, "C")] if score >= floor), "NONE"),
                  metrics=dict(ema5=emas[0][-1], ema10=emas[1][-1], ema20=emas[2][-1],
                               spreadNow=now, spreadMean3=avg3, spreadMean5=avg5,
                               spreadMax5=maximum, spreadStd5=deviation,
                               spreadMean10=mean(spread[-10:]), spreadMax10=max(spread[-10:]),
                               historicalPercentile=percentile, ema20Change5=slope,
                               compressionChange=change, compressionStreak=streak),
                  componentScores=components)
    for label, value, limit in zip(labels, measured, cfg["extreme"]):
        passed = value <= limit
        result["reasons" if passed else "failReasons"].append(
            f"{label} {value:.4f}% {'≤' if passed else '>'} {limit:g}%")
    return result
