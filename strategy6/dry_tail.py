"""Strategy6 non-overlapping dry and stable tail evaluation."""
from __future__ import annotations

from strategy6.indicators import _return_between, _return_over
from strategy6.models import Strategy6DryTail, Strategy6Indicators, Strategy6Phase


def evaluate_dry_tail(
    rows: list[dict],
    ind: Strategy6Indicators,
    phase: Strategy6Phase,
    config: dict,
) -> Strategy6DryTail:
    if not phase.valid:
        return Strategy6DryTail(rejects=[phase.status])
    tail = rows[phase.tail_start_index:phase.signal_index + 1]
    pre_tail = rows[max(0, phase.tail_start_index - 20):phase.tail_start_index]
    if len(tail) < int(config["tail_window_days"]) or len(pre_tail) < 20:
        return Strategy6DryTail(rejects=["TAIL_VOLUME_BASE_INSUFFICIENT"])

    tail_avg = _mean(row["volume"] for row in tail)
    pre_tail_avg = _mean(row["volume"] for row in pre_tail)
    ratio = tail_avg / pre_tail_avg if pre_tail_avg > 0 else 0.0
    volume_slope = _volume_slope(rows[-10:])
    score = 0
    reasons: list[str] = []
    rejects: list[str] = []
    recent_5_low_close = min((row["close"] for row in tail), default=0.0)
    pre_tail_recent_low_close = min((row["close"] for row in pre_tail[-5:]), default=0.0)
    split = max(1, len(tail) // 2)
    early_tail_low = min((row["low"] for row in tail[:split]), default=0.0)
    late_tail_low = min((row["low"] for row in tail[split:]), default=0.0)
    max_drop_3d = min(
        (_return_between(prev["close"], curr["close"]) for prev, curr in zip(rows[-4:-1], rows[-3:])),
        default=0.0,
    )

    if ind.has_big_down_volume:
        rejects.append("BIG_DOWN_VOLUME")
    if pre_tail_recent_low_close > 0 and recent_5_low_close < pre_tail_recent_low_close:
        rejects.append("TAIL_NEW_LOW")
    if early_tail_low > 0 and late_tail_low < early_tail_low * 0.99:
        rejects.append("TAIL_LOW_DECLINING")
    if ind.close_range_5 > config["tail_close_range_5"]:
        rejects.append("TAIL_CLOSE_RANGE_GT_8PCT")
    if ratio > config["tail_volume_ratio_5_20"]:
        rejects.append("TAIL_VOLUME_NOT_DRY")
    if ind.return_5 < config["tail_min_return_5"]:
        rejects.append("TAIL_RETURN_5_TOO_WEAK")
    if max_drop_3d <= config["tail_min_return_3"]:
        rejects.append("TAIL_SINGLE_DROP_TOO_WEAK")

    if ratio <= config["tail_volume_ratio_5_20"]:
        score += 6
        reasons.append("volume:non_overlap_tail_dry")
    if ratio <= config["tail_strong_volume_ratio_5_20"]:
        score += 2
        reasons.append("volume:non_overlap_tail_strong_dry")
    if pre_tail_recent_low_close > 0 and recent_5_low_close >= pre_tail_recent_low_close:
        score += 4
        reasons.append("price:no_new_low")
    if 0 < ind.close_range_5 <= config["tail_close_range_5"]:
        score += 4
        reasons.append("price:close_range_stable")
    if ind.return_5 >= config["tail_min_return_5"]:
        score += 2
        reasons.append("price:return_5_stable")
    if volume_slope < 0:
        score += 2
        reasons.append("volume:slope_down")
    if not ind.has_big_down_volume:
        score += 2
        reasons.append("risk:no_big_down_volume")
    return Strategy6DryTail(
        dry_stable_score=min(20, score),
        dry_tail_pass=not rejects,
        reasons=reasons,
        rejects=rejects,
        tail_avg_volume=round(tail_avg, 4),
        pre_tail_avg_volume_20=round(pre_tail_avg, 4),
        tail_volume_ratio=round(ratio, 6),
        volume_slope_10=round(volume_slope, 6),
    )


def _volume_slope(rows: list[dict]) -> float:
    if len(rows) < 2:
        return 0.0
    n = len(rows)
    x_mean = (n - 1) / 2
    y_mean = _mean(row["volume"] for row in rows)
    denominator = sum((idx - x_mean) ** 2 for idx in range(n))
    if denominator <= 0 or y_mean <= 0:
        return 0.0
    numerator = sum((idx - x_mean) * (row["volume"] - y_mean) for idx, row in enumerate(rows))
    return numerator / denominator / y_mean


def _mean(values) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0
