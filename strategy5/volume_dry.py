"""Strategy5 volume dry evaluation."""
from __future__ import annotations

from strategy5.models import Strategy5Indicators, Strategy5VolumeDry


def evaluate_strategy5_volume_dry(ind: Strategy5Indicators, config: dict) -> Strategy5VolumeDry:
    """Evaluate post-sprint volume dry quality for Strategy5."""
    score = 0
    reasons: list[str] = []
    warnings: list[str] = []
    rejects: list[str] = []

    if ind.v20 <= 0 or ind.v5 <= 0:
        return Strategy5VolumeDry(
            volume_dry_score=0,
            volume_dry_level="BAD_DRY",
            volume_dry_rejects=["DRY_INVALID_VOLUME"],
        )

    if ind.has_big_down_volume:
        rejects.append("DRY_BIG_DOWN_VOLUME")
    if ind.consecutive_heavy_bear_days >= int(config["volume_dry_consecutive_bear_days"]):
        rejects.append("DRY_CONSECUTIVE_HEAVY_BEAR")
    if (
        ind.volume_ratio_5_20 <= 0.70
        and ind.recent_5d_return < -0.05
        and (not ind.no_new_low_5 or ind.close < ind.ma20)
    ):
        rejects.append("DRY_SHRINKING_BEAR_DRIFT")

    if ind.volume_ratio_5_20 <= config["volume_dry_ratio_5_20"]:
        score += 2
        reasons.append("volume:dry")
    if ind.volume_ratio_5_20 <= config["volume_dry_strong_ratio_5_20"]:
        score += 2
        reasons.append("volume:strong_dry")
    if ind.volume_ratio_5_20 <= config["volume_dry_extreme_ratio_5_20"]:
        reasons.append("volume:extreme_dry")
    if 0 < ind.volume_ratio_5_50 <= config["volume_dry_ratio_5_50"]:
        score += 1
        reasons.append("volume:v5_below_v50")
    if 0 < ind.volume_percentile_60 <= config["volume_dry_percentile_60"]:
        score += 1
        reasons.append("volume:low_volume_percentile")

    if 0 < ind.v3 < ind.v5 < ind.v10 < ind.v20:
        score += 3
        reasons.append("volume:v3_v5_v10_v20_contracting")
    elif 0 < ind.v5 < ind.v10 < ind.v20:
        score += 2
        reasons.append("volume:v5_v10_v20_contracting")
    elif 0 < ind.v5 < ind.v20:
        score += 1
        reasons.append("volume:v5_below_v20")

    if ind.down_day_avg_volume_ratio_20 == 0 or ind.down_day_avg_volume_ratio_20 <= config["volume_dry_down_day_avg_ratio_20"]:
        score += 2
        reasons.append("volume:down_day_volume_below_v20")
    if ind.down_volume_ratio_5 <= config["volume_dry_down_volume_ratio_5"]:
        score += 1
        reasons.append("volume:down_volume_exhausted")
    if not ind.has_big_down_volume:
        score += 1
        reasons.append("volume:no_big_down_volume")

    if ind.close >= ind.ma10 > 0:
        score += 1
        reasons.append("price:close_above_ma10")
    if ind.close >= ind.ma20 > 0:
        score += 1
        reasons.append("price:close_above_ma20")
    if ind.no_new_low_5:
        score += 1
        reasons.append("price:no_new_low_5")
    if ind.dry_support_valid:
        score += 1
        reasons.append("support:dry_support_valid")

    if 0 < ind.close_range_5 <= config["volume_dry_close_range_5"]:
        score += 1
        reasons.append("price:close_range_tight")
    if (
        0 < ind.atr_ratio_5_20 <= config["volume_dry_atr_contract_ratio"]
        or 0 < ind.direction_efficiency_5 <= config["volume_dry_direction_efficiency"]
    ):
        score += 1
        reasons.append("price:volatility_contracted")

    score = min(score, 20)
    if _has_volume_stall(ind, config):
        score = min(score, 12)
        warnings.append("DRY_VOLUME_STALL")

    level = _level(score, rejects)
    return Strategy5VolumeDry(
        volume_dry_score=score,
        volume_dry_level=level,
        volume_dry_reasons=_dedupe(reasons),
        volume_dry_warnings=_dedupe(warnings),
        volume_dry_rejects=_dedupe(rejects),
    )


def _level(score: int, rejects: list[str]) -> str:
    if rejects:
        return "BAD_DRY"
    if score >= 17:
        return "EXTREME_DRY"
    if score >= 14:
        return "HEALTHY_DRY"
    if score >= 10:
        return "WATCH_DRY"
    return "NOT_DRY"


def _has_volume_stall(ind: Strategy5Indicators, config: dict) -> bool:
    return (
        ind.volume_ratio_5_20 >= 1.5
        and ind.recent_5d_return < 0.03
        and ind.close_range_5 > config["volume_dry_close_range_5"]
    )


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
