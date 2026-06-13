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
Bad-shrink cap: if price trending down while volume shrinking, cap at 6
Low-position cap: if price near 60d low, cap accordingly
Volume-stall cap: if heavy volume without price advance, cap at 6
"""

from dataclasses import dataclass, field

DEFAULT_VD_CFG = {
    "bad_shrink_max_score": 7,
    "bad_shrink_slope_pct": -3,
    "min_position_60d_normal": 0.5,
    "low_position_max_score": 7,
    "very_low_position_max_score": 6,
    "volume_stall_multiplier": 1.5,
    "volume_stall_max_score": 7,
    "big_bear_max_score": 6,
    "big_bear_volume_multiplier": 1.5,
    "big_bear_drop_pct": 3,
}


@dataclass
class VolumeDryResult:
    total_score: int = 0
    raw_score: int = 0
    sub_scores: dict = field(default_factory=dict)
    verdict: str = "不建议买入"
    details: list = field(default_factory=list)
    caps: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    reject_reasons: list = field(default_factory=list)


def _avg(seq):
    if not seq:
        return 0.0
    return sum(seq) / len(seq)


def _linear_regression_slope(y_values):
    """Return slope of linear regression as percentage of the first value."""
    n = len(y_values)
    if n < 2:
        return 0.0
    x_avg = (n - 1) / 2.0
    y_avg = _avg(y_values)
    num = sum((i - x_avg) * (y - y_avg) for i, y in enumerate(y_values))
    den = sum((i - x_avg) ** 2 for i in range(n))
    if den == 0:
        return 0.0
    slope = num / den
    return (slope * (n - 1) / y_values[0]) * 100 if y_values[0] != 0 else 0.0


def score_volume_dry(data: list[dict], config: dict | None = None) -> VolumeDryResult:
    """Calculate Volume Dry Score from daily OHLC data.

    Requires at least 50 trading days of data.

    Args:
        config: 来自 config.yaml 的 volume_dry 段。
    """
    cfg = {**DEFAULT_VD_CFG, **(config or {})}
    result = VolumeDryResult()

    if not data or len(data) < 50:
        return result

    volumes = [d["volume"] for d in data]
    closes = [d["close"] for d in data]
    highs = [d["high"] for d in data]
    lows = [d["low"] for d in data]

    ma20 = _avg(volumes[-20:])
    ma50 = _avg(volumes[-50:])

    # Recent 5-day average volume
    v5 = _avg(volumes[-5:])

    score_a = 0; score_b = 0; score_c = 0; score_d = 0; score_e = 0

    # A. Recent volume vs MA20 (max 3 pts)
    if ma20 > 0:
        ratio_a = v5 / ma20
        if ratio_a <= 0.80:
            score_a = 3
            result.details.append(f"V5/MA20={ratio_a:.2f} <= 0.80: +3")
        elif ratio_a <= 0.90:
            score_a = 2
            result.details.append(f"V5/MA20={ratio_a:.2f} <= 0.90: +2")
        elif ratio_a <= 1.00:
            score_a = 1
            result.details.append(f"V5/MA20={ratio_a:.2f} <= 1.00: +1")
        else:
            result.details.append(f"V5/MA20={ratio_a:.2f} > 1.00: +0")
    result.sub_scores["A_volume_vs_ma20"] = score_a

    # B. Recent volume vs MA50 (max 3 pts)
    if ma50 > 0:
        ratio_b = v5 / ma50
        if ratio_b <= 0.70:
            score_b = 3
            result.details.append(f"V5/MA50={ratio_b:.2f} <= 0.70: +3")
        elif ratio_b <= 0.85:
            score_b = 2
            result.details.append(f"V5/MA50={ratio_b:.2f} <= 0.85: +2")
        elif ratio_b <= 1.00:
            score_b = 1
            result.details.append(f"V5/MA50={ratio_b:.2f} <= 1.00: +1")
        else:
            result.details.append(f"V5/MA50={ratio_b:.2f} > 1.00: +0")
    result.sub_scores["B_volume_vs_ma50"] = score_b

    # C. Consolidation end volume decreasing (max 3 pts)
    if len(volumes) >= 15:
        v1 = _avg(volumes[-15:-10])
        v2 = _avg(volumes[-10:-5])
        v3 = v5
        if v1 > v2 > v3 and v1 > 0:
            score_c = 3
            result.details.append(f"V1({v1:.0f}) > V2({v2:.0f}) > V3({v3:.0f}): +3")
        elif v2 > v3 and v2 > 0:
            score_c = 2
            result.details.append(f"V2({v2:.0f}) > V3({v3:.0f}): +2")
        elif v1 > v2 and v2 > 0:
            score_c = 1
            result.details.append("V1 > V2 (非严格递减): +1")
        else:
            result.details.append("Volume not decreasing: +0")
    result.sub_scores["C_shrinking_sequence"] = score_c

    # D. Down day volume analysis (max 1.5 pts)
    down_vols = []
    for i in range(max(0, len(data) - 10), len(data)):
        if i > 0 and closes[i] < closes[i - 1]:
            down_vols.append(volumes[i])
    if not down_vols:
        score_d = 1.5
        result.details.append("No down days in last 10: +1.5")
    elif ma20 > 0:
        avg_down_vol = _avg(down_vols)
        ratio_d = avg_down_vol / ma20
        if ratio_d <= 0.90:
            score_d = 1.5
            result.details.append(f"Down day avg vol/MA20={ratio_d:.2f} <= 0.90: +1.5")
        elif ratio_d <= 1.05:
            score_d = 1.0
            result.details.append(f"Down day avg vol/MA20={ratio_d:.2f} <= 1.05: +1.0")
        else:
            result.details.append(f"Down day avg vol/MA20={ratio_d:.2f} > 1.05: +0")
    result.sub_scores["D_down_day_volume"] = score_d

    # E. Extreme low volume (max 1.5 pts)
    if ma50 > 0:
        min_v5 = min(volumes[-5:])
        ratio_e = min_v5 / ma50
        if ratio_e <= 0.50:
            score_e = 1.5
            result.details.append(f"Min V5/MA50={ratio_e:.2f} <= 0.50: +1.5")
        elif ratio_e <= 0.65:
            score_e = 1.0
            result.details.append(f"Min V5/MA50={ratio_e:.2f} <= 0.65: +1.0")
        elif ratio_e <= 0.80:
            score_e = 0.5
            result.details.append(f"Min V5/MA50={ratio_e:.2f} <= 0.80: +0.5")
        else:
            result.details.append(f"Min V5/MA50={ratio_e:.2f} > 0.80: +0")
    result.sub_scores["E_extreme_low"] = score_e

    raw_total = score_a + score_b + score_c + score_d + score_e
    result.raw_score = min(raw_total, 12)
    result.total_score = result.raw_score

    # --- Capping rules ---

    # 1. Big bear breakdown cap (existing, refined)
    big_bear_mult = float(cfg["big_bear_volume_multiplier"])
    big_bear_drop = float(cfg["big_bear_drop_pct"])
    for i in range(max(0, len(data) - 3), len(data)):
        if i > 0 and closes[i] < closes[i - 1] * (1 - big_bear_drop / 100):
            if ma20 > 0 and volumes[i] >= ma20 * big_bear_mult:
                cap = int(cfg["big_bear_max_score"])
                result.total_score = min(result.total_score, cap)
                result.caps.append(f"近3日放量大阴线，量干最高{cap}分")
                result.reject_reasons.append("近3日存在放量大阴线，卖压未释放完毕")
                break

    # 2. Bad shrink: price declining while volume shrinking
    if len(data) >= 10:
        slope_pct = _linear_regression_slope(closes[-10:])
        bad_shrink_slope = float(cfg["bad_shrink_slope_pct"])
        if slope_pct < bad_shrink_slope and closes[-1] < _avg(closes[-20:]):
            cap = int(cfg["bad_shrink_max_score"])
            result.total_score = min(result.total_score, cap)
            result.caps.append(f"缩量但价格重心下移({slope_pct:.1f}%)，量干最高{cap}分")
            result.warnings.append("缩量但价格重心下移，疑似弱势阴跌")

    # 3. Low position capping
    if len(data) >= 60:
        high_60d = max(highs[-60:])
        low_60d = min(lows[-60:])
        if high_60d > low_60d:
            pos_60d = (closes[-1] - low_60d) / (high_60d - low_60d)
            if pos_60d < 0.3:
                cap = int(cfg["very_low_position_max_score"])
                result.total_score = min(result.total_score, cap)
                result.caps.append(f"股价处于近60日低位区(pos={pos_60d:.2f})，量干最高{cap}分")
                result.reject_reasons.append("股价处于近60日低位区，缩量不代表卖压衰竭")
            elif pos_60d < float(cfg["min_position_60d_normal"]):
                cap = int(cfg["low_position_max_score"])
                result.total_score = min(result.total_score, cap)
                result.caps.append(f"缩量位置偏低(pos={pos_60d:.2f})，量干最高{cap}分")
                result.warnings.append("缩量位置偏低，弱势缩量风险")

    # 4. Volume stall: heavy volume without price advance
    stall_mult = float(cfg["volume_stall_multiplier"])
    for i in range(max(0, len(data) - 5), len(data)):
        if ma20 > 0 and volumes[i] >= ma20 * stall_mult:
            day_change = (closes[i] / closes[i - 1] - 1) * 100 if i > 0 else 0
            close_pos = (closes[i] - lows[i]) / (highs[i] - lows[i]) if highs[i] > lows[i] else 0.5
            if day_change < 1 and close_pos < 0.5:
                cap = int(cfg["volume_stall_max_score"])
                result.total_score = min(result.total_score, cap)
                result.caps.append(f"近5日存在放量滞涨，量干最高{cap}分")
                result.warnings.append("近5日存在放量滞涨，上方抛压仍在")
                break

    # Verdict (scaled for max 12)
    if result.total_score >= 9:
        result.verdict = "可低吸"
    elif result.total_score >= 7:
        result.verdict = "观察"
    else:
        result.verdict = "不建议买入"

    return result
