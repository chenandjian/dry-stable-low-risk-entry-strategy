"""Strategy6 hard filters and candidate classification."""
from __future__ import annotations

from dataclasses import replace

from strategy6.models import (
    Strategy6BoxTail,
    Strategy6DryTail,
    Strategy6Indicators,
    Strategy6Phase,
    Strategy6Pattern,
    Strategy6Score,
    Strategy6SelectionDiagnostics,
    Strategy6EntryTiming,
    Strategy6ProbabilityAdjustedRR,
    Strategy6SetupQuality,
    Strategy6StrongTrendSqueeze,
    Strategy6Start,
    Strategy6Support,
    Strategy6TradePlan,
)
from strategy6.entry_quality import (
    entry_quality_blocks_tier,
    entry_quality_hard_filter_reasons,
)
from strategy6.brooks.models import BrooksTailResult
from strategy6.strong_start import PASSING_START_TYPES
from strategy6.validation import is_strategy6_research_profile


def selection_hard_filter_reasons(
    diagnostics: Strategy6SelectionDiagnostics,
    config: dict,
) -> list[str]:
    experiment = config["selection_optimization"]
    reasons: list[str] = []
    if (
        experiment["support_confirmation_enabled"]
        and diagnostics.support_confirmation_status == "FAILED"
    ):
        reasons.append("SUPPORT_CONFIRMATION_FAILED")
    if (
        experiment["tail_deterioration_filter_enabled"]
        and diagnostics.recent_tail_status == "DETERIORATING"
    ):
        reasons.append("RECENT_TAIL_DETERIORATING")
    return reasons


def selection_blocks_ready(
    diagnostics: Strategy6SelectionDiagnostics,
    config: dict,
) -> bool:
    experiment = config["selection_optimization"]
    return any((
        experiment["support_confirmation_enabled"]
        and diagnostics.support_confirmation_status != "CONFIRMED",
        experiment["rs_fading_downgrade_enabled"]
        and diagnostics.relative_strength_trend == "FADING",
        experiment["matched_market_downgrade_enabled"]
        and diagnostics.matched_market_status in {"MARKET_WEAK", "MARKET_RISK"},
    ))


def selection_rr(
    trade_plan: Strategy6TradePlan,
    diagnostics: Strategy6SelectionDiagnostics,
    config: dict,
) -> float:
    if config["selection_optimization"]["conservative_rr_enabled"]:
        return diagnostics.conservative_rr
    return trade_plan.objective_rr_2


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
    selection_diagnostics: Strategy6SelectionDiagnostics | None = None,
    entry_timing: Strategy6EntryTiming | None = None,
    probability_rr: Strategy6ProbabilityAdjustedRR | None = None,
    strong_trend_squeeze: Strategy6StrongTrendSqueeze | None = None,
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
    if strong_trend_squeeze is not None:
        reasons.extend(strong_trend_squeeze.reasons)
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
    research_profile = is_strategy6_research_profile(config)
    reasons.extend(reason for reason in dry_tail.rejects if reason in structural_tail_rejects)
    if not research_profile or (
        (box_tail is None or not box_tail.passed)
        and (brooks_tail is None or not brooks_tail.passed)
    ):
        reasons.extend(dry_tail.rejects)
    if (
        research_profile
        and quality.distribution_day_count >= 3
        and "DISTRIBUTION_PRESSURE_HIGH" in quality.risk_tags
    ):
        reasons.append("DISTRIBUTION_PRESSURE_HIGH")
    if research_profile and "SUPPORT_VOLUME_BREAK_UNRECOVERED" in support.support_reaction_risk_tags:
        reasons.append("SUPPORT_VOLUME_BREAK_UNRECOVERED")
    diagnostics = selection_diagnostics or Strategy6SelectionDiagnostics()
    reasons.extend(selection_hard_filter_reasons(diagnostics, config))
    reasons.extend(entry_quality_hard_filter_reasons(
        entry_timing or Strategy6EntryTiming(),
        probability_rr or Strategy6ProbabilityAdjustedRR(),
        config,
    ))
    effective_rr = selection_rr(trade_plan, diagnostics, config)
    if effective_rr < config["rr2_min_watch"]:
        threshold = str(config["rr2_min_watch"]).replace(".", "_")
        prefix = (
            "CONSERVATIVE_RR_LT"
            if config["selection_optimization"]["conservative_rr_enabled"]
            else "RR2_LT"
        )
        reasons.append(f"{prefix}_{threshold}")
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
    selection_diagnostics: Strategy6SelectionDiagnostics | None = None,
    entry_timing: Strategy6EntryTiming | None = None,
    probability_rr: Strategy6ProbabilityAdjustedRR | None = None,
) -> tuple[str, str, str, str]:
    research_profile = is_strategy6_research_profile(config)
    lifecycle = _lifecycle_status(
        ind, phase, support, dry_tail, trade_plan, reject_reasons, config,
        box_tail=box_tail,
        brooks_tail=brooks_tail,
    )
    if reject_reasons:
        return "REJECTED", "rejected", lifecycle, "排除：存在硬性风险或盈亏比不足"
    major_risk = any(tag in ind.risk_tags for tag in {"BIG_DOWN_VOLUME"})
    diagnostics = selection_diagnostics or Strategy6SelectionDiagnostics()
    timing = entry_timing or Strategy6EntryTiming()
    adjusted_probability = probability_rr or Strategy6ProbabilityAdjustedRR()
    effective_rr = selection_rr(trade_plan, diagnostics, config)
    environment_blocks_ready = (
        _environment_blocks_ready(ind)
        or selection_blocks_ready(diagnostics, config)
    )
    tactical_blocks_ready = _tactical_blocks_ready(ind, start, support)
    if phase.status == "START_TOO_RECENT":
        return "WATCH_CANDIDATE", "observe", "START_CONFIRMED", "观察：强势启动已确认，等待独立整理阶段"
    if research_profile and _brooks_only_waiting_for_trigger(dry_tail, box_tail, brooks_tail):
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
    if research_profile and _single_auxiliary_path(dry_tail, box_tail, brooks_tail):
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
        and effective_rr >= config["rr2_min_ready"]
        and support.support_zone_low <= ind.current_price <= support.support_zone_high
        and dry_tail.tail_volume_ratio <= config["tail_strong_volume_ratio_5_20"]
        and support.support_status in {"PATTERN_SUPPORT", "MA20_SUPPORT", "KEY_SUPPORT_VALID"}
        and start.start_grade != "B"
        and (research_profile or dry_tail.dry_tail_pass)
        and _quality_threshold_met(
            score.setup_quality_score,
            config["setup_quality_min_ready"],
            score.score_model_version,
        )
        and _quality_threshold_met(
            score.support_reaction_score,
            config["support_reaction_min_ready"],
            score.score_model_version,
        )
        and not major_risk
        and not environment_blocks_ready
        and not tactical_blocks_ready
        and not entry_quality_blocks_tier(
            "READY_CANDIDATE", timing, adjusted_probability, config,
        )
    ):
        return "READY_CANDIDATE", "ready", lifecycle, "低吸候选：支撑区内，量干价稳，盈亏比较好"
    if (
        score.total_score >= config["key_min_score"]
        and effective_rr >= config["rr2_min_key"]
        and support.support_status in {"PATTERN_SUPPORT", "MA20_SUPPORT", "KEY_SUPPORT_VALID"}
        and (
            score.tail_score >= 15
            if research_profile
            else dry_tail.dry_tail_pass and dry_tail.dry_stable_score >= 15
        )
        and start.start_grade != "B"
        and _quality_threshold_met(
            score.setup_quality_score,
            config["setup_quality_min_key"],
            score.score_model_version,
        )
        and _quality_threshold_met(
            score.support_reaction_score,
            config["support_reaction_min_key"],
            score.score_model_version,
        )
        and not major_risk
        and not environment_blocks_ready
        and not tactical_blocks_ready
        and not entry_quality_blocks_tier(
            "KEY_CANDIDATE", timing, adjusted_probability, config,
        )
    ):
        return "KEY_CANDIDATE", "highlight", lifecycle, "重点观察：等待支撑低吸或突破确认"
    if score.total_score >= config["watch_min_score"]:
        return "WATCH_CANDIDATE", "observe", lifecycle, "观察：形态部分满足，等待进一步确认"
    return "REJECTED", "rejected", lifecycle, "排除：评分不足"


def classify_candidate_before_market_downgrade(
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
    selection_diagnostics: Strategy6SelectionDiagnostics | None = None,
    entry_timing: Strategy6EntryTiming | None = None,
    probability_rr: Strategy6ProbabilityAdjustedRR | None = None,
) -> str:
    """Return the tier before weak-market downgrade without mutating indicators."""
    audit_indicators = replace(
        ind,
        market_filter_enabled=False,
        warn_tags=[
            tag for tag in ind.warn_tags
            if tag not in {"MARKET_WEAK_DOWNGRADED", "MARKET_WEAK_STRICT"}
        ],
    )
    candidate_type, *_ = classify_candidate(
        audit_indicators,
        start,
        phase,
        pattern,
        support,
        dry_tail,
        trade_plan,
        score,
        reject_reasons,
        config,
        box_tail=box_tail,
        brooks_tail=brooks_tail,
        selection_diagnostics=selection_diagnostics,
        entry_timing=entry_timing,
        probability_rr=probability_rr,
    )
    return candidate_type


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


def _quality_threshold_met(value: int, threshold: float, score_model_version: str) -> bool:
    # Empty model versions represent legacy direct callers that never
    # calculated quality fields. V2 evaluations treat a real zero as zero.
    if score_model_version != "S6_QUALITY_V2":
        return True
    return value >= threshold


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
    if dry_tail.dry_tail_pass or (
        is_strategy6_research_profile(config)
        and (
            (box_tail is not None and box_tail.passed)
            or (brooks_tail is not None and brooks_tail.passed)
        )
    ):
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
