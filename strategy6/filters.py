"""Strategy6 hard filters and candidate classification."""
from __future__ import annotations

from strategy6.models import (
    Strategy6BoxTail,
    Strategy6DryTail,
    Strategy6Indicators,
    Strategy6Phase,
    Strategy6Pattern,
    Strategy6Score,
    Strategy6SetupQuality,
    Strategy6Start,
    Strategy6Support,
    Strategy6TradePlan,
)
from strategy6.brooks.models import BrooksTailResult
from strategy6.strong_start import PASSING_START_TYPES


def hard_filter_reasons(
    rows: list[dict],
    ind: Strategy6Indicators,
    start: Strategy6Start,
    phase: Strategy6Phase,
    pattern: Strategy6Pattern,
    support: Strategy6Support,
    dry_tail: Strategy6DryTail,
    trade_plan: Strategy6TradePlan,
    config: dict,
    *,
    box_tail: Strategy6BoxTail | None = None,
    brooks_tail: BrooksTailResult | None = None,
    setup_quality: Strategy6SetupQuality | None = None,
) -> list[str]:
    reasons: list[str] = []
    if not phase.valid and phase.status != "START_TOO_RECENT":
        reasons.append(phase.status)
    if (
        config["pattern_filter_enabled"]
        and config["pattern_filter_mode"] == "strict"
        and pattern.pattern_type == "UNKNOWN"
    ):
        reasons.append("PATTERN_UNKNOWN")
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
    # A valid start younger than the minimum consolidation age is a lifecycle
    # observation; mature support, tail and objective-target filters do not
    # have an independent phase to evaluate yet.
    if phase.status == "START_TOO_RECENT":
        return _dedupe(reasons)
    reasons.extend(_consolidation_filter_reasons(ind, start, config))
    if support.support_status == "SUPPORT_FAILED":
        reasons.append("SUPPORT_FAILED")
    elif support.support_test_count < 1:
        reasons.append("NO_VALID_SUPPORT_TEST")
    reasons.extend(_shape_failure_reasons(rows, ind, support, config))
    if ind.ma50 > 0 and ind.current_price < ind.ma50 * config["ma50_min_ratio"]:
        reasons.append("CLOSE_LT_MA50_0_92")
    quality = setup_quality or Strategy6SetupQuality()
    structural_tail_rejects = {
        "BIG_DOWN_VOLUME", "TAIL_NEW_LOW", "TAIL_LOW_DECLINING",
        "TAIL_RETURN_5_TOO_WEAK", "TAIL_SINGLE_DROP_TOO_WEAK",
    }
    reasons.extend(reason for reason in dry_tail.rejects if reason in structural_tail_rejects)
    if (box_tail is None or not box_tail.passed) and (brooks_tail is None or not brooks_tail.passed):
        reasons.extend(dry_tail.rejects)
    if quality.distribution_day_count >= 3 and "DISTRIBUTION_PRESSURE_HIGH" in quality.risk_tags:
        reasons.append("DISTRIBUTION_PRESSURE_HIGH")
    if "SUPPORT_VOLUME_BREAK_UNRECOVERED" in support.support_reaction_risk_tags:
        reasons.append("SUPPORT_VOLUME_BREAK_UNRECOVERED")
    if trade_plan.objective_rr_2 < config["rr2_min_watch"]:
        threshold = str(config["rr2_min_watch"]).replace(".", "_")
        reasons.append(f"RR2_LT_{threshold}")
    return _dedupe(reasons)


def classify_candidate(
    ind: Strategy6Indicators,
    start: Strategy6Start,
    phase: Strategy6Phase,
    pattern: Strategy6Pattern,
    support: Strategy6Support,
    dry_tail: Strategy6DryTail,
    trade_plan: Strategy6TradePlan,
    score: Strategy6Score,
    reject_reasons: list[str],
    config: dict,
    *,
    box_tail: Strategy6BoxTail | None = None,
    brooks_tail: BrooksTailResult | None = None,
) -> tuple[str, str, str, str]:
    lifecycle = _lifecycle_status(
        ind, phase, support, dry_tail, trade_plan, reject_reasons, config,
        box_tail=box_tail,
        brooks_tail=brooks_tail,
    )
    if reject_reasons:
        return "REJECTED", "rejected", lifecycle, "排除：存在硬性风险或盈亏比不足"
    major_risk = any(tag in ind.risk_tags for tag in {"BIG_DOWN_VOLUME"})
    environment_blocks_ready = _environment_blocks_ready(ind)
    tactical_blocks_ready = _tactical_blocks_ready(ind, start, support)
    if phase.status == "START_TOO_RECENT":
        return "WATCH_CANDIDATE", "observe", "START_CONFIRMED", "观察：强势启动已确认，等待独立整理阶段"
    if _brooks_only_waiting_for_trigger(dry_tail, box_tail, brooks_tail):
        return (
            "WATCH_CANDIDATE",
            "observe",
            "SETUP_FORMING",
            "观察等待触发：Brooks结构成立，但交易触发尚未确认",
        )
    if trade_plan.entry_archetype == "WAIT_BREAKOUT":
        return (
            "WATCH_CANDIDATE",
            "observe",
            "SETUP_FORMING",
            "观察：结构有效，等待突破平台上沿后确认",
        )
    if _single_auxiliary_path(dry_tail, box_tail, brooks_tail):
        return (
            "WATCH_CANDIDATE",
            "observe",
            "SETUP_FORMING",
            "观察：单一辅助路径仅作证据，等待原始量价或第二路径确认",
        )
    if (
        config["pattern_filter_enabled"]
        and config["pattern_filter_mode"] == "downgrade"
        and pattern.pattern_type == "UNKNOWN"
    ):
        return "WATCH_CANDIDATE", "observe", lifecycle, "观察：形态尚未明确"
    if (
        score.total_score >= config["ready_min_score"]
        and trade_plan.objective_rr_2 >= config["rr2_min_ready"]
        and support.support_zone_low <= ind.current_price <= support.support_zone_high
        and dry_tail.tail_volume_ratio <= config["tail_strong_volume_ratio_5_20"]
        and support.support_status in {"PATTERN_SUPPORT", "MA20_SUPPORT", "KEY_SUPPORT_VALID"}
        and start.start_grade != "B"
        and _quality_threshold_met(score.setup_quality_score, config["setup_quality_min_ready"])
        and _quality_threshold_met(score.support_reaction_score, config["support_reaction_min_ready"])
        and not major_risk
        and not environment_blocks_ready
        and not tactical_blocks_ready
    ):
        return "READY_CANDIDATE", "ready", lifecycle, "低吸候选：支撑区内，量干价稳，盈亏比较好"
    if (
        score.total_score >= config["key_min_score"]
        and trade_plan.objective_rr_2 >= config["rr2_min_key"]
        and support.support_status in {"PATTERN_SUPPORT", "MA20_SUPPORT", "KEY_SUPPORT_VALID"}
        and score.tail_score >= 15
        and start.start_grade != "B"
        and _quality_threshold_met(score.setup_quality_score, config["setup_quality_min_key"])
        and _quality_threshold_met(score.support_reaction_score, config["support_reaction_min_key"])
        and not major_risk
        and not environment_blocks_ready
        and not tactical_blocks_ready
    ):
        return "KEY_CANDIDATE", "highlight", lifecycle, "重点观察：等待支撑低吸或突破确认"
    if score.total_score >= config["watch_min_score"] or trade_plan.objective_rr_2 >= config["rr2_min_watch"]:
        return "WATCH_CANDIDATE", "observe", lifecycle, "观察：形态部分满足，等待进一步确认"
    return "REJECTED", "rejected", lifecycle, "排除：评分不足"


def _brooks_only_waiting_for_trigger(
    dry_tail: Strategy6DryTail,
    box_tail: Strategy6BoxTail | None,
    brooks_tail: BrooksTailResult | None,
) -> bool:
    return bool(
        brooks_tail is not None
        and brooks_tail.passed
        and not brooks_tail.trade_trigger.ready
        and not dry_tail.dry_tail_pass
        and (box_tail is None or not box_tail.passed)
    )


def _single_auxiliary_path(
    dry_tail: Strategy6DryTail,
    box_tail: Strategy6BoxTail | None,
    brooks_tail: BrooksTailResult | None,
) -> bool:
    if dry_tail.dry_tail_pass:
        return False
    count = int(bool(box_tail is not None and box_tail.passed)) + int(
        bool(brooks_tail is not None and brooks_tail.passed)
    )
    return count == 1


def _quality_threshold_met(value: int, threshold: float) -> bool:
    # Zero is the compatibility value used by direct legacy callers and old
    # task snapshots. Engine V2 evaluations always calculate these fields.
    return value == 0 or value >= threshold


def _lifecycle_status(
    ind: Strategy6Indicators,
    phase: Strategy6Phase,
    support: Strategy6Support,
    dry_tail: Strategy6DryTail,
    trade_plan: Strategy6TradePlan,
    reject_reasons: list[str],
    config: dict,
    *,
    box_tail: Strategy6BoxTail | None = None,
    brooks_tail: BrooksTailResult | None = None,
) -> str:
    if phase.lifecycle_status in {"START_CONFIRMED", "EXPIRED"}:
        return phase.lifecycle_status
    if _is_extended_breakout(ind, support, config):
        if "BREAKOUT_EXTENDED" not in ind.warn_tags:
            ind.warn_tags.append("BREAKOUT_EXTENDED")
        return "EXTENDED"
    if _has_shape_failure(reject_reasons):
        return "FAILED"
    if _is_quality_breakout(ind, support):
        return "BREAKOUT_CONFIRMED"
    if trade_plan.suggested_buy_price and support.support_zone_low <= ind.current_price <= support.support_zone_high:
        return "BUY_ZONE"
    if dry_tail.dry_tail_pass or (box_tail is not None and box_tail.passed) or (brooks_tail is not None and brooks_tail.passed):
        return "READY"
    return "SETUP_FORMING"


def _environment_blocks_ready(ind: Strategy6Indicators) -> bool:
    blocked = False
    if ind.market_filter_enabled and not ind.relative_strength_20_observed:
        if "RS20_DATA_UNAVAILABLE" not in ind.warn_tags:
            ind.warn_tags.append("RS20_DATA_UNAVAILABLE")
        blocked = True
    if ind.market_filter_enabled and ind.market_status == "UNKNOWN":
        if "MARKET_DATA_UNAVAILABLE" not in ind.warn_tags:
            ind.warn_tags.append("MARKET_DATA_UNAVAILABLE")
        blocked = True
    if ind.market_filter_enabled and ind.market_filter_mode in {"strict", "downgrade"}:
        if ind.market_status in {"MARKET_WEAK", "MARKET_RISK"}:
            if ind.market_filter_mode == "strict":
                if "MARKET_WEAK_STRICT" not in ind.warn_tags:
                    ind.warn_tags.append("MARKET_WEAK_STRICT")
            else:
                if "MARKET_WEAK_DOWNGRADED" not in ind.warn_tags:
                    ind.warn_tags.append("MARKET_WEAK_DOWNGRADED")
            blocked = True
    return blocked


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
    if support.pivot_price > 0 and ind.current_price > support.pivot_price * (
        1 + float(config["breakout_extended_max_pct"])
    ):
        reasons.append("BREAKOUT_EXTENDED")
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
        "BREAKOUT_EXTENDED",
    })


def _is_quality_breakout(ind: Strategy6Indicators, support: Strategy6Support) -> bool:
    if support.pivot_price <= 0 or ind.current_price <= support.pivot_price:
        return False
    distance = ind.current_price / support.pivot_price - 1
    return (
        ind.current_volume_ratio_20 >= 1.3
        and _close_position_is_strong(ind)
        and ind.daily_return <= 0.09
        and distance <= 0.05
    )


def _is_extended_breakout(ind: Strategy6Indicators, support: Strategy6Support, config: dict) -> bool:
    if support.pivot_price <= 0 or ind.current_price <= support.pivot_price:
        return False
    return ind.current_price > support.pivot_price * (1 + float(config["breakout_extended_max_pct"]))


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
