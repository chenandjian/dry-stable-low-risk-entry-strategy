# strategy2/scorer.py
"""策略2评分 — 量干50分、价稳50分、等级计算。"""
from strategy2.models import Strategy2Indicators, Strategy2Score


def score_volume_dry(ind: Strategy2Indicators) -> tuple[int, list[str]]:
    """计算量干评分，满分50。

    Returns:
        (score, reasons) — score 0-50, reasons 为命中评分项列表。
    """
    score = 0
    reasons = []

    # 1. V5 / V20 <= 0.60: +10
    if ind.volume_ratio_5_20 <= 0.60:
        score += 10
        reasons.append(f"V5/V20 <= 0.60: +10 (实际 {ind.volume_ratio_5_20:.3f})")

    # 2. V5 / V20 <= 0.50: extra +10
    if ind.volume_ratio_5_20 <= 0.50:
        score += 10
        reasons.append(f"V5/V20 <= 0.50: +10 (实际 {ind.volume_ratio_5_20:.3f})")

    # 3. V3 < V5 < V10 < V20: +10
    if ind.v3 < ind.v5 < ind.v10 < ind.v20:
        score += 10
        reasons.append(f"V3 < V5 < V10 < V20: +10 (V3={ind.v3:.0f} V5={ind.v5:.0f} V10={ind.v10:.0f} V20={ind.v20:.0f})")

    # 4. 最近5日中至少一天成交量处于近60日最低20%: +10
    if ind.volume_percentile <= 20.0:
        score += 10
        reasons.append(f"成交量处于近60日最低20%: +10 (分位 {ind.volume_percentile:.1f}%)")

    # 5. return_5 >= -3%: +10
    if ind.return_5 >= -0.03:
        score += 10
        reasons.append(f"return_5 >= -3%: +10 (实际 {ind.return_5:.3f})")

    return score, reasons


def score_price_stable(
    ind: Strategy2Indicators,
    has_no_big_drop: bool = True,
    close_above_support: bool = True,
) -> tuple[int, list[str]]:
    """计算价稳评分，满分50。

    Args:
        ind: 指标结果。
        has_no_big_drop: 最近5日不存在单日跌幅低于-3%。
        close_above_support: 当前收盘价不低于 key_support。

    Returns:
        (score, reasons)
    """
    score = 0
    reasons = []

    # 1. range_5 <= 5%: +10
    if ind.range_5 <= 0.05:
        score += 10
        reasons.append(f"range_5 <= 5%: +10 (实际 {ind.range_5:.3f})")

    # 2. range_5 <= 3%: extra +10
    if ind.range_5 <= 0.03:
        score += 10
        reasons.append(f"range_5 <= 3%: +10 (实际 {ind.range_5:.3f})")

    # 3. close_range_5 <= 3%: +10
    if ind.close_range_5 <= 0.03:
        score += 10
        reasons.append(f"close_range_5 <= 3%: +10 (实际 {ind.close_range_5:.3f})")

    # 4. 最近5日不存在单日跌幅低于 -3%: +10
    if has_no_big_drop:
        score += 10
        reasons.append("最近5日无单日跌幅低于-3%: +10")

    # 5. 当前收盘价不低于 key_support: +10
    if close_above_support:
        score += 10
        reasons.append("当前收盘价不低于 key_support: +10")

    return score, reasons


def compute_total_score(
    ind: Strategy2Indicators,
    has_no_big_drop: bool = True,
    close_above_support: bool = True,
) -> Strategy2Score:
    """计算总分并确定等级。

    Returns:
        Strategy2Score 包含量干分、价稳分、总分、等级和命中评分项。
    """
    vol_score, vol_reasons = score_volume_dry(ind)
    price_score, price_reasons = score_price_stable(ind, has_no_big_drop, close_above_support)

    total = vol_score + price_score

    # 等级判定
    if total >= 95:
        level = "终极状态"
    elif total >= 90:
        level = "极致量干价稳"
    elif total >= 80:
        level = "重点观察"
    elif total >= 70:
        level = "普通观察"
    else:
        level = ""

    return Strategy2Score(
        volume_dry_score=vol_score,
        price_stable_score=price_score,
        total_score=total,
        level=level,
        score_reasons=vol_reasons + price_reasons,
    )
