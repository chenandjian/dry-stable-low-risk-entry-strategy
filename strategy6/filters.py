"""Strategy6 hard filters and candidate classification."""
from __future__ import annotations

from strategy6.models import (
    Strategy6DryTail,
    Strategy6Indicators,
    Strategy6Score,
    Strategy6Start,
    Strategy6Support,
    Strategy6TradePlan,
)
from strategy6.strong_start import PASSING_START_TYPES


def hard_filter_reasons(
    rows: list[dict],
    ind: Strategy6Indicators,
    start: Strategy6Start,
    support: Strategy6Support,
    dry_tail: Strategy6DryTail,
    trade_plan: Strategy6TradePlan,
    config: dict,
) -> list[str]:
    reasons: list[str] = []
    if ind.trading_days < config["minimum_trading_days"]:
        reasons.append(f"TRADING_DAYS_LT_{config['minimum_trading_days']}")
    if min(ind.ma5, ind.ma10, ind.ma20, ind.ma50, ind.ma120, ind.ma250) <= 0:
        reasons.append("MA_CALC_FAILED")
    if ind.ma250 > 0 and ind.current_price <= ind.ma250:
        reasons.append("CLOSE_LE_MA250")
    if ind.ma120 > 0 and ind.ma250 > 0 and ind.ma120 <= ind.ma250:
        reasons.append("MA120_LE_MA250")
    if ind.amount_avg_60 < config["min_avg_amount_60d_yi"]:
        reasons.append("AVG60D_LT_MIN")
    if ind.amount_avg_30 < config["min_avg_amount_30d_yi"]:
        reasons.append("AVG30D_LT_MIN")
    if ind.amount_avg_10 < config["min_avg_amount_10d_yi"]:
        reasons.append("AVG10D_LT_MIN")
    if ind.amount_avg_30 > 0 and ind.amount_avg_10 < ind.amount_avg_30 * config["amount10_vs_30_min_ratio"]:
        reasons.append("AVG10D_LT_AVG30D_RATIO")
    if ind.relative_strength_20_observed and ind.relative_strength_20 < config["min_relative_strength_20"]:
        threshold = str(config["min_relative_strength_20"]).replace(".", "_")
        reasons.append(f"RS20_LT_{threshold}")
    if start.start_type not in PASSING_START_TYPES and not (start.start_type == "B_GRADE_MOMENTUM" and start.start_grade == "B"):
        reasons.append("NO_STRONG_START")
    if not start.high_trigger:
        reasons.append("NO_NEW_HIGH_CONFIRMATION")
    reasons.extend(_consolidation_filter_reasons(ind, start, config))
    if support.support_status == "SUPPORT_FAILED":
        reasons.append("SUPPORT_FAILED")
    elif support.support_test_count < 1:
        reasons.append("NO_VALID_SUPPORT_TEST")
    reasons.extend(_shape_failure_reasons(rows, ind, support, config))
    if ind.ma50 > 0 and ind.current_price < ind.ma50 * config["ma50_min_ratio"]:
        reasons.append("CLOSE_LT_MA50_0_92")
    reasons.extend(dry_tail.rejects)
    if trade_plan.risk_reward_ratio_2 < config["rr2_min_watch"]:
        threshold = str(config["rr2_min_watch"]).replace(".", "_")
        reasons.append(f"RR2_LT_{threshold}")
    return _dedupe(reasons)


def classify_candidate(
    ind: Strategy6Indicators,
    start: Strategy6Start,
    support: Strategy6Support,
    dry_tail: Strategy6DryTail,
    trade_plan: Strategy6TradePlan,
    score: Strategy6Score,
    reject_reasons: list[str],
    config: dict,
) -> tuple[str, str, str, str]:
    lifecycle = _lifecycle_status(ind, support, dry_tail, trade_plan, reject_reasons)
    if reject_reasons:
        return "REJECTED", "rejected", lifecycle, "排除：存在硬性风险或盈亏比不足"
    major_risk = any(tag in ind.risk_tags for tag in {"BIG_DOWN_VOLUME"})
    environment_blocks_ready = _environment_blocks_ready(ind)
    tactical_blocks_ready = _tactical_blocks_ready(ind, start, support)
    if (
        score.total_score >= config["ready_min_score"]
        and trade_plan.risk_reward_ratio_2 >= config["rr2_min_ready"]
        and support.support_zone_low <= ind.current_price <= support.support_zone_high
        and ind.volume_ratio_5_20 <= config["tail_strong_volume_ratio_5_20"]
        and support.support_status in {"MA5_SUPPORT", "MA10_SUPPORT", "MA20_SUPPORT"}
        and start.start_grade != "B"
        and not major_risk
        and not environment_blocks_ready
        and not tactical_blocks_ready
    ):
        return "READY_CANDIDATE", "ready", lifecycle, "低吸候选：支撑区内，量干价稳，盈亏比较好"
    if (
        score.total_score >= config["key_min_score"]
        and trade_plan.risk_reward_ratio_2 >= config["rr2_min_key"]
        and support.support_status in {"MA5_SUPPORT", "MA10_SUPPORT", "MA20_SUPPORT"}
        and dry_tail.dry_stable_score >= 15
        and start.start_grade != "B"
        and not major_risk
        and not environment_blocks_ready
        and not tactical_blocks_ready
    ):
        return "KEY_CANDIDATE", "highlight", lifecycle, "重点观察：等待支撑低吸或突破确认"
    if score.total_score >= config["watch_min_score"] or trade_plan.risk_reward_ratio_2 >= config["rr2_min_watch"]:
        return "WATCH_CANDIDATE", "observe", lifecycle, "观察：形态部分满足，等待进一步确认"
    return "REJECTED", "rejected", lifecycle, "排除：评分不足"


def _lifecycle_status(
    ind: Strategy6Indicators,
    support: Strategy6Support,
    dry_tail: Strategy6DryTail,
    trade_plan: Strategy6TradePlan,
    reject_reasons: list[str],
) -> str:
    if _is_extended_breakout(ind, support):
        if "BREAKOUT_EXTENDED" not in ind.warn_tags:
            ind.warn_tags.append("BREAKOUT_EXTENDED")
        return "EXTENDED"
    if _has_shape_failure(reject_reasons):
        return "FAILED"
    if trade_plan.suggested_buy_price and ind.current_price > support.pivot_price * 1.08:
        return "EXTENDED"
    if _is_quality_breakout(ind, support):
        return "BREAKOUT_CONFIRMED"
    if trade_plan.suggested_buy_price and support.support_zone_low <= ind.current_price <= support.support_zone_high:
        return "BUY_ZONE"
    if dry_tail.dry_tail_pass:
        return "READY"
    return "SETUP_FORMING"


def _environment_blocks_ready(ind: Strategy6Indicators) -> bool:
    if ind.market_filter_enabled and ind.market_filter_mode in {"strict", "downgrade"}:
        if ind.market_status in {"MARKET_WEAK", "MARKET_RISK"}:
            if ind.market_filter_mode == "strict":
                ind.warn_tags.append("MARKET_WEAK_STRICT")
            else:
                ind.warn_tags.append("MARKET_WEAK_DOWNGRADED")
            return True
    if ind.sector_filter_enabled and ind.sector_filter_mode in {"strict", "downgrade"}:
        if ind.sector_strength_status in {"SECTOR_WEAK", "SECTOR_RISK"}:
            if ind.sector_filter_mode == "strict":
                ind.warn_tags.append("SECTOR_WEAK_STRICT")
            else:
                ind.warn_tags.append("SECTOR_WEAK_DOWNGRADED")
            return True
    return False


def _tactical_blocks_ready(ind: Strategy6Indicators, start: Strategy6Start, support: Strategy6Support) -> bool:
    blocked = False
    if "UPPER_SHADOW_PRESSURE" in ind.warn_tags or "PRESSURE_NEAR_HIGH" in ind.warn_tags:
        blocked = True
    if start.start_type == "ONE_WORD_LIMIT_UP" and not _one_word_limit_up_confirmed(ind, start, support):
        if "ONE_WORD_LIMIT_UP_UNCONFIRMED" not in ind.warn_tags:
            ind.warn_tags.append("ONE_WORD_LIMIT_UP_UNCONFIRMED")
        blocked = True
    return blocked


def _one_word_limit_up_confirmed(ind: Strategy6Indicators, start: Strategy6Start, support: Strategy6Support) -> bool:
    if start.days_since_start < 3:
        return False
    if ind.current_price < start.start_low:
        return False
    if ind.has_big_down_volume:
        return False
    if support.support_status not in {"MA5_SUPPORT", "MA10_SUPPORT", "MA20_SUPPORT"}:
        return False
    if ind.volume_ratio_5_20 > 0.75:
        return False
    return True


def _shape_failure_reasons(rows: list[dict], ind: Strategy6Indicators, support: Strategy6Support, config: dict) -> list[str]:
    reasons: list[str] = []
    failure_support = support.prior_key_support_price or support.key_support_price
    if failure_support > 0 and ind.current_price < failure_support * 0.96:
        reasons.append("CLOSE_LT_KEY_SUPPORT_0_96")
    if support.key_support_price > 0 and ind.current_price < support.key_support_price:
        reasons.append("CLOSE_LT_KEY_SUPPORT")
    if failure_support > 0 and len(rows) >= 2 and all(
        row["close"] < failure_support for row in rows[-2:]
    ):
        reasons.append("TWO_CLOSES_LT_KEY_SUPPORT")
    if ind.has_big_down_volume:
        reasons.append("BIG_DOWN_VOLUME")
    if ind.ma50 > 0 and ind.current_price < ind.ma50 * config["ma50_min_ratio"]:
        reasons.append("CLOSE_LT_MA50_0_92")
    return reasons


def _has_shape_failure(reject_reasons: list[str]) -> bool:
    return any(reason in reject_reasons for reason in {
        "BIG_DOWN_VOLUME",
        "SUPPORT_FAILED",
        "CLOSE_LT_KEY_SUPPORT_0_96",
        "TWO_CLOSES_LT_KEY_SUPPORT",
        "CLOSE_LT_MA50_0_92",
    })


def _is_quality_breakout(ind: Strategy6Indicators, support: Strategy6Support) -> bool:
    if support.pivot_price <= 0 or ind.current_price <= support.pivot_price:
        return False
    distance = ind.current_price / support.pivot_price - 1
    return (
        ind.volume_ratio_5_20 >= 1.3
        and _close_position_is_strong(ind)
        and ind.daily_return <= 0.09
        and distance <= 0.05
    )


def _is_extended_breakout(ind: Strategy6Indicators, support: Strategy6Support) -> bool:
    if support.pivot_price <= 0 or ind.current_price <= support.pivot_price:
        return False
    return ind.current_price > support.pivot_price * 1.08


def _close_position_is_strong(ind: Strategy6Indicators) -> bool:
    return ind.current_close_position >= 0.65


def _consolidation_filter_reasons(ind: Strategy6Indicators, start: Strategy6Start, config: dict) -> list[str]:
    reasons: list[str] = []
    grade = start.start_grade.lower()
    if grade in {"s", "a", "b"}:
        amp5_limit = config.get(f"max_amp_5d_{grade}")
        amp10_limit = config.get(f"max_amp_10d_{grade}")
        pullback_limit = config.get(f"max_pullback_20d_{grade}")
        if amp5_limit is not None and ind.range_5 > amp5_limit:
            reasons.append(f"CONSOLIDATION_RANGE_5_GT_{grade.upper()}_LIMIT")
        if amp10_limit is not None and ind.range_10 > amp10_limit:
            reasons.append(f"CONSOLIDATION_RANGE_10_GT_{grade.upper()}_LIMIT")
        if pullback_limit is not None and ind.pullback_from_20d_high < pullback_limit:
            reasons.append(f"CONSOLIDATION_PULLBACK_20D_GT_{grade.upper()}_LIMIT")
    if ind.range_10 > config["absolute_max_amp_10d"]:
        reasons.append("CONSOLIDATION_RANGE_10_GT_ABSOLUTE_LIMIT")
    if ind.pullback_from_20d_high < config["absolute_max_pullback_20d"]:
        reasons.append("CONSOLIDATION_PULLBACK_20D_GT_ABSOLUTE_LIMIT")
    return reasons


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
