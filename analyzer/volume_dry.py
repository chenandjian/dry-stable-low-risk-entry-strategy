# analyzer/volume_dry.py
"""Volume Dry Score (量干评分) — 判断卖压是否枯竭。

Scoring dimensions (0-10):
  A. Recent volume vs MA20 (max 2 pts)
  B. Recent volume vs MA50 (max 2 pts)
  C. Consolidation end volume decreasing (max 2 pts)
  D. Down days no heavy volume (max 2 pts)
  E. Extreme low volume appearance (max 2 pts)

Hard rule: score < 6 → can NOT be "可低吸"
Breakdown cap: if last 3 days has volume breakdown candle, cap score at 5
"""

from dataclasses import dataclass, field


@dataclass
class VolumeDryResult:
    total_score: int = 0
    sub_scores: dict = field(default_factory=dict)
    verdict: str = "不建议买入"
    details: list = field(default_factory=list)


def _avg(seq):
    if not seq:
        return 0.0
    return sum(seq) / len(seq)


def score_volume_dry(data: list[dict]) -> VolumeDryResult:
    """Calculate Volume Dry Score from daily OHLC data.

    Requires at least 50 trading days of data.
    """
    result = VolumeDryResult()

    if not data or len(data) < 50:
        return result

    volumes = [d["volume"] for d in data]
    closes = [d["close"] for d in data]

    ma20 = _avg(volumes[-20:])
    ma50 = _avg(volumes[-50:])

    # Recent 5-day average volume
    v5 = _avg(volumes[-5:])

    # Track each dimension's score independently
    score_a = 0
    score_b = 0
    score_c = 0
    score_d = 0
    score_e = 0

    # A. Recent volume vs MA20 (max 2 pts)
    if ma20 > 0:
        ratio_a = v5 / ma20
        if ratio_a <= 0.80:
            score_a = 2
            result.details.append(f"V5/MA20={ratio_a:.2f} <= 0.80: +2")
        elif ratio_a <= 0.90:
            score_a = 1
            result.details.append(f"V5/MA20={ratio_a:.2f} <= 0.90: +1")
        else:
            result.details.append(f"V5/MA20={ratio_a:.2f} > 0.90: +0")
    result.sub_scores["A_volume_vs_ma20"] = score_a

    # B. Recent volume vs MA50 (max 2 pts)
    if ma50 > 0:
        ratio_b = v5 / ma50
        if ratio_b <= 0.70:
            score_b = 2
            result.details.append(f"V5/MA50={ratio_b:.2f} <= 0.70: +2")
        elif ratio_b <= 0.85:
            score_b = 1
            result.details.append(f"V5/MA50={ratio_b:.2f} <= 0.85: +1")
        else:
            result.details.append(f"V5/MA50={ratio_b:.2f} > 0.85: +0")
    result.sub_scores["B_volume_vs_ma50"] = score_b

    # C. Consolidation end volume decreasing (max 2 pts)
    if len(volumes) >= 15:
        v1 = _avg(volumes[-15:-10])  # 15-11 days ago
        v2 = _avg(volumes[-10:-5])   # 10-6 days ago
        v3 = v5                      # last 5 days
        if v1 > v2 > v3 and v1 > 0:
            score_c = 2
            result.details.append(f"V1({v1:.0f}) > V2({v2:.0f}) > V3({v3:.0f}): +2")
        elif v2 > v3 and v2 > 0:
            score_c = 1
            result.details.append(f"V2({v2:.0f}) > V3({v3:.0f}): +1")
        else:
            result.details.append("Volume not decreasing: +0")
    result.sub_scores["C_shrinking_sequence"] = score_c

    # D. Down day volume analysis (max 2 pts)
    down_vols = []
    for i in range(max(0, len(data) - 10), len(data)):
        if i > 0 and closes[i] < closes[i - 1]:
            down_vols.append(volumes[i])
    if not down_vols:
        score_d = 2
        result.details.append("No down days in last 10: +2")
    elif ma20 > 0:
        avg_down_vol = _avg(down_vols)
        ratio_d = avg_down_vol / ma20
        if ratio_d <= 0.90:
            score_d = 2
            result.details.append(f"Down day avg vol/MA20={ratio_d:.2f} <= 0.90: +2")
        elif ratio_d <= 1.05:
            score_d = 1
            result.details.append(f"Down day avg vol/MA20={ratio_d:.2f} <= 1.05: +1")
        else:
            result.details.append(f"Down day avg vol/MA20={ratio_d:.2f} > 1.05: +0")
    result.sub_scores["D_down_day_volume"] = score_d

    # E. Extreme low volume (max 2 pts)
    if ma50 > 0:
        min_v5 = min(volumes[-5:])
        ratio_e = min_v5 / ma50
        if ratio_e <= 0.50:
            score_e = 2
            result.details.append(f"Min V5/MA50={ratio_e:.2f} <= 0.50: +2")
        elif ratio_e <= 0.65:
            score_e = 1
            result.details.append(f"Min V5/MA50={ratio_e:.2f} <= 0.65: +1")
        else:
            result.details.append(f"Min V5/MA50={ratio_e:.2f} > 0.65: +0")
    result.sub_scores["E_extreme_low"] = score_e

    total = score_a + score_b + score_c + score_d + score_e
    result.total_score = min(total, 10)

    # Breakdown check: last 3 days — volume spike on a >=3% down day
    for i in range(max(0, len(data) - 3), len(data)):
        if i > 0 and closes[i] < closes[i - 1] * 0.97:  # >= -3%
            if ma20 > 0 and volumes[i] >= ma20 * 1.5:     # volume >= 1.5x MA20
                result.total_score = min(result.total_score, 5)
                result.details.append("BREAKDOWN: score capped at 5")
                break

    # Verdict
    if result.total_score >= 7:
        result.verdict = "可低吸"
    elif result.total_score >= 6:
        result.verdict = "观察"
    else:
        result.verdict = "不建议买入"

    return result
