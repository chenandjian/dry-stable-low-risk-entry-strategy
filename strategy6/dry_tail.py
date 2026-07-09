"""Strategy6 dry and stable tail evaluation."""
from __future__ import annotations

from strategy6.indicators import _return_over
from strategy6.models import Strategy6DryTail, Strategy6Indicators


def evaluate_dry_tail(rows: list[dict], ind: Strategy6Indicators, config: dict) -> Strategy6DryTail:
    score = 0
    reasons: list[str] = []
    rejects: list[str] = []
    recent_5_low_close = min((r["close"] for r in rows[-5:]), default=0.0)
    recent_10_low_close = min((r["close"] for r in rows[-10:]), default=0.0)
    return_3 = _return_over(rows, 3)

    if ind.has_big_down_volume:
        rejects.append("BIG_DOWN_VOLUME")
    if recent_5_low_close < recent_10_low_close:
        rejects.append("TAIL_NEW_LOW")
    if ind.close_range_5 > config["tail_close_range_5"]:
        rejects.append("TAIL_CLOSE_RANGE_GT_8PCT")
    if ind.volume_ratio_5_20 > config["tail_volume_ratio_5_20"]:
        rejects.append("TAIL_VOLUME_NOT_DRY")
    if ind.return_5 < config["tail_min_return_5"]:
        rejects.append("TAIL_RETURN_5_TOO_WEAK")
    if return_3 < config["tail_min_return_3"]:
        rejects.append("TAIL_RETURN_3_TOO_WEAK")

    if ind.volume_ratio_5_20 <= config["tail_volume_ratio_5_20"]:
        score += 6
        reasons.append("volume:v5_v20_dry")
    if ind.volume_ratio_5_20 <= config["tail_strong_volume_ratio_5_20"]:
        score += 4
        reasons.append("volume:v5_v20_strong_dry")
    if 0 < ind.v3 < ind.v5 < ind.v10 < ind.v20:
        score += 5
        reasons.append("volume:v3_v5_v10_v20_contracting")
    if recent_5_low_close >= recent_10_low_close:
        score += 4
        reasons.append("price:no_new_low")
    if 0 < ind.close_range_5 <= config["tail_close_range_5"]:
        score += 4
        reasons.append("price:close_range_stable")
    if not ind.has_big_down_volume:
        score += 2
        reasons.append("risk:no_big_down_volume")
    return Strategy6DryTail(
        dry_stable_score=min(25, score),
        dry_tail_pass=not rejects,
        reasons=reasons,
        rejects=rejects,
    )

