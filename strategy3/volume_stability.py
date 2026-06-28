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
    if ind.volume_ratio_5_20 <= config["dry_volume_ratio"] and ind.return_5 <= config["dry_return_5_reject"]:
        rejects.append("SHRINKING_BEAR_DRIFT")
    if (
        ind.support_price_10 > 0
        and ind.support_status in {"WEAKENING", "BROKEN", "FAILED"}
    ):
        rejects.append("SUPPORT_TEST_FAILED")
    if ind.atr_ratio_5_20 >= config["dry_atr_expand_reject_ratio"] and ind.return_5 < 0:
        rejects.append("DOWNSIDE_VOLATILITY_EXPANDING")
    if ind.has_big_down_volume:
        rejects.append("DRY_HEAVY_DOWNSIDE_VOLUME")

    score = 0
    dry_base = 0.0
    if ind.volume_ratio_5_20 <= config["volume_shrink_ratio"]:
        dry_base += 2
        reasons.append("volume_ratio_5_20<=shrink_ratio")
    if ind.volume_ratio_5_20 <= config["dry_volume_ratio"]:
        dry_base += 1.5
        reasons.append("volume_dry")
    if 0 < ind.v3 < ind.v5 < ind.v10 < ind.v20:
        dry_base += 1.5
        reasons.append("v3<v5<v10<v20")
    score += int(round(min(dry_base, 5)))

    if ind.return_5 >= config["dry_return_5_floor"]:
        score += 2
        reasons.append("return_5_stable")
    if ind.no_new_low:
        score += 2
        reasons.append("no_new_low")
    if ind.close_range_5 <= 0.05:
        score += 2
        reasons.append("close_range_tight")
    if ind.close_range_5 <= config["dry_balance_close_range_tight"]:
        score += 1
        reasons.append("close_range_extreme_tight")

    if ind.direction_efficiency_5 <= config["dry_balance_direction_efficiency_threshold"]:
        score += 2
        reasons.append("direction_efficiency_low")
    if ind.direction_efficiency_5 <= config["dry_balance_extreme_direction_efficiency_threshold"]:
        score += 1
        reasons.append("direction_efficiency_extreme")
    if (
        ind.max_up_5 <= config["dry_balance_max_up_5"]
        and ind.max_down_5 >= config["dry_balance_max_down_5"]
    ):
        score += 1
        reasons.append("max_daily_move_balanced")
    if (
        config["dry_balance_close_position_min"]
        <= ind.avg_close_position_5
        <= config["dry_balance_close_position_max"]
    ):
        score += 1
        reasons.append("close_position_balanced")
    if ind.range_compression_ok:
        score += 1
        reasons.append("range_compression_sequence")

    if ind.support_test_count >= config["dry_support_min_test_count"]:
        score += 2
        reasons.append(f"support_test_count>={config['dry_support_min_test_count']}")
    if ind.support_valid:
        score += 2
        reasons.append("support_valid")
    if ind.support_status in {"VALID", "TESTING"}:
        reasons.append(f"support_status:{ind.support_status}")

    if ind.bear_body_shrink:
        score += 1
        reasons.append("bear_body_shrink")
    if ind.lower_shadow_count >= config["dry_lower_shadow_min_count"]:
        score += 1
        reasons.append("lower_shadow_support")
    if ind.down_volume_ratio_5 <= config["dry_down_volume_ratio_max"] and not ind.has_big_down_volume:
        score += 1
        reasons.append("down_volume_ratio_ok")

    if ind.atr_ratio_5_20 > 0 and ind.atr_ratio_5_20 <= config["dry_atr_contract_ratio"]:
        score += 1
        reasons.append("atr_contracted")
    if ind.atr_ratio_5_20 > 0 and ind.atr_ratio_5_20 <= config["dry_atr_extreme_contract_ratio"]:
        score += 1
        reasons.append("atr_extreme_contracted")

    if not _lows_declining(data[-5:]):
        reasons.append("lows_stable")
    if ind.down_day_volume_ratio == 0 or ind.down_day_volume_ratio < 1.0:
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
