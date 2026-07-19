"""Brooks tail-path scoring and final candidate decision."""
from __future__ import annotations

from strategy6.brooks.models import (
    BrooksCompactStructureResult,
    BrooksContextResult,
    BrooksSellingPressureResult,
    BrooksStructureResult,
    BrooksTailResult,
)
from strategy6.brooks.compact import classify_compact_structure
from strategy6.brooks.context import analyze_brooks_context, support_effectively_broken
from strategy6.brooks.metrics import bar_metrics, find_swing_lows
from strategy6.brooks.selling_pressure import analyze_selling_pressure
from strategy6.brooks.structures import analyze_brooks_structures
from strategy6.models import (
    Strategy6CompactKline,
    Strategy6DryTail,
    Strategy6Indicators,
    Strategy6Phase,
    Strategy6Start,
    Strategy6Support,
)


def analyze_brooks_tail(
    rows: list[dict],
    indicators: Strategy6Indicators,
    start: Strategy6Start,
    phase: Strategy6Phase,
    support: Strategy6Support,
    dry_tail: Strategy6DryTail,
    compact_metrics: Strategy6CompactKline,
    *,
    config: dict,
) -> BrooksTailResult:
    if not config["enabled"]:
        return BrooksTailResult.disabled()
    if not phase.valid:
        return BrooksTailResult(
            enabled=True,
            status="BROOKS_FAILED",
            reject_reasons=[phase.status or "BROOKS_PHASE_INVALID"],
        )

    context = analyze_brooks_context(rows, indicators, start, support, config)
    selling = analyze_selling_pressure(rows, support, config)
    compact = classify_compact_structure(
        rows,
        compact_metrics,
        context,
        support,
        selling,
        atr14=indicators.atr14,
        config=config,
    )
    structure_start = phase.consolidation_start_index
    structure_rows = (
        rows[structure_start:]
        if 0 <= structure_start < len(rows)
        else []
    )
    structures = analyze_brooks_structures(
        structure_rows,
        support,
        selling,
        compact_structure_type=compact.structure_type,
        atr14=indicators.atr14,
        tail_volume_ratio=dry_tail.tail_volume_ratio,
        config=config,
    )
    stability = _price_stability_checks(rows, compact_metrics, config)
    volume_dry_pass = (
        dry_tail.tail_volume_ratio > 0
        and dry_tail.tail_volume_ratio <= float(config["volume_dry"]["tail_volume_ratio_max"])
        and not indicators.has_big_down_volume
    )
    volume_dry_premium = (
        volume_dry_pass
        and dry_tail.tail_volume_ratio <= float(config["volume_dry"]["premium_tail_volume_ratio_max"])
        and (not config["volume_dry"]["require_volume_slope_negative"] or dry_tail.volume_slope_10 < 0)
    )
    support_not_broken = not support_effectively_broken(
        rows,
        support,
        float(config["support"]["effective_break_pct"]),
        int(config["support"]["consecutive_close_break_days"]),
    )
    result = score_brooks_tail(
        context=context,
        selling=selling,
        compact=compact,
        structure=structures,
        price_stability_checks=stability,
        volume_dry_pass=volume_dry_pass,
        volume_dry_premium=volume_dry_premium,
        support_not_broken=support_not_broken,
        config=config,
    )
    result.metrics.update({
        "close_range_5": compact_metrics.close_range,
        "avg_body_ratio_5": compact_metrics.avg_body_ratio,
        "max_body_ratio_5": compact_metrics.max_body_ratio,
        "atr_contraction_ratio": compact_metrics.atr_contraction_ratio,
        "tail_volume_ratio": dry_tail.tail_volume_ratio,
        "volume_slope_10": dry_tail.volume_slope_10,
    })
    return result


def _price_stability_checks(
    rows: list[dict],
    compact: Strategy6CompactKline,
    config: dict,
) -> dict[str, bool]:
    cfg = config["price_stability"]
    window = rows[-int(cfg["compact_window_days"]):]
    metrics = [bar_metrics(row) for row in window]
    valid = len(window) == int(cfg["compact_window_days"]) and all(metric.valid for metric in metrics)
    closes = [float(row.get("close") or 0) for row in window]
    close_range = max(closes) / min(closes) - 1 if valid and min(closes) > 0 else float("inf")
    average_body = sum(metric.body_ratio or 0 for metric in metrics) / len(metrics) if valid else float("inf")
    maximum_body = max((metric.body_ratio or 0 for metric in metrics), default=float("inf"))
    atr_ratio = compact.atr_contraction_ratio
    swing_lows = find_swing_lows(rows[-max(10, int(cfg["compact_window_days"]) + 2):])
    lower_lows = True
    if len(swing_lows) >= 2:
        lower_lows = swing_lows[-1].price >= swing_lows[-2].price * (
            1 - float(cfg["low_similarity_tolerance"])
        )
    return {
        "close_range": close_range <= float(cfg["close_range_max"]),
        "atr": atr_ratio is not None and atr_ratio <= float(cfg["atr_contraction_max"]),
        "body_avg": average_body <= float(cfg["avg_body_ratio_max"]),
        "body_max": maximum_body <= float(cfg["max_body_ratio_max"]),
        "lower_lows": lower_lows,
    }


def score_brooks_tail(
    *,
    context: BrooksContextResult,
    selling: BrooksSellingPressureResult,
    compact: BrooksCompactStructureResult,
    structure: BrooksStructureResult,
    price_stability_checks: dict[str, bool],
    volume_dry_pass: bool,
    volume_dry_premium: bool,
    support_not_broken: bool,
    config: dict,
) -> BrooksTailResult:
    scoring = config["scoring"]
    context_score = int(scoring["context_points"]) if context.passed else 0

    selling_score = 0
    selling_score += 2 if selling.strong_bear_bar_count == 0 else 0
    selling_score += 2 if selling.bear_follow_through_count == 0 else 0
    selling_score += 1 if selling.max_consecutive_bear_bars <= int(config["selling_pressure"]["max_consecutive_bear_bars"]) else 0
    selling_score += 1 if selling.exhausted else 0
    selling_score = min(int(scoring["selling_pressure_points"]), selling_score)

    stability_score = 0
    stability_score += int(bool(price_stability_checks.get("close_range")))
    stability_score += int(bool(price_stability_checks.get("atr")))
    stability_score += int(bool(price_stability_checks.get("body_avg") and price_stability_checks.get("body_max")))
    stability_score += int(bool(
        price_stability_checks.get("lower_lows")
        and compact.structure_type in {"COMPACT_ORDERLY", "NO_COMPACT"}
    ))
    stability_score = min(int(scoring["price_stability_points"]), stability_score)

    volume_score = int(volume_dry_pass) + int(volume_dry_pass and volume_dry_premium)
    volume_score = min(int(scoring["volume_dry_points"]), volume_score)
    setup_score = _setup_score(structure)
    setup_score = min(int(scoring["setup_points"]), setup_score)
    score = context_score + selling_score + stability_score + volume_score + setup_score

    hard_reject = compact.structure_type == "COMPACT_BEARISH" or not support_not_broken
    price_stable_pass = all(price_stability_checks.values()) and compact.structure_type != "COMPACT_BEARISH"
    passed = all((
        context.passed,
        selling.exhausted,
        price_stable_pass,
        volume_dry_pass,
        support_not_broken,
        structure.passed,
        not hard_reject,
        score >= int(scoring["pass_score_min"]),
    ))
    result = BrooksTailResult(
        enabled=True,
        passed=passed,
        score=score,
        premium=passed and score >= int(scoring["premium_score_min"]),
        status=_status(compact, structure, context, support_not_broken, passed),
        bull_context_pass=context.passed,
        selling_pressure_exhausted=selling.exhausted,
        price_stable_pass=price_stable_pass,
        volume_dry_pass=volume_dry_pass,
        support_not_broken=support_not_broken,
        setup_pass=structure.passed,
        hard_reject=hard_reject,
        context=context,
        selling_pressure=selling,
        compact_structure=compact,
        structure=structure,
        metrics={"price_stability_checks": dict(price_stability_checks)},
    )
    if passed:
        result.reasons.append("BROOKS_TAIL_PATH_PASSED")
    else:
        result.reject_reasons.extend(_reject_reasons(result, compact))
    return result


def _setup_score(structure: BrooksStructureResult) -> int:
    if structure.second_entry_long_ready:
        return 4
    if structure.failed_bear_breakout:
        return 3
    if structure.micro_double_bottom:
        return 2
    if structure.orderly_compression_at_support or structure.bear_follow_through_failed:
        return 1
    return 0


def _status(
    compact: BrooksCompactStructureResult,
    structure: BrooksStructureResult,
    context: BrooksContextResult,
    support_not_broken: bool,
    passed: bool,
) -> str:
    if not support_not_broken:
        return "SUPPORT_BROKEN"
    if compact.structure_type == "COMPACT_BEARISH":
        return "COMPACT_BEARISH_REJECT"
    if not context.passed:
        return "BROOKS_CONTEXT_REJECT"
    if compact.structure_type == "BARB_WIRE":
        return "BARB_WIRE_WAIT"
    if structure.second_entry_long_ready:
        return "SECOND_ENTRY_LONG_READY"
    if structure.failed_bear_breakout:
        return "FAILED_BEAR_BREAKOUT"
    if structure.micro_double_bottom:
        return "MICRO_DOUBLE_BOTTOM"
    if structure.orderly_compression_at_support:
        return "ORDERLY_COMPRESSION_AT_SUPPORT"
    if passed:
        return "BROOKS_WATCH"
    return "BROOKS_FAILED"


def _reject_reasons(result: BrooksTailResult, compact: BrooksCompactStructureResult) -> list[str]:
    reasons: list[str] = []
    if not result.bull_context_pass:
        reasons.append("BROOKS_CONTEXT_REJECT")
    if not result.selling_pressure_exhausted:
        reasons.append("BROOKS_SELLING_PRESSURE_NOT_EXHAUSTED")
    if not result.price_stable_pass:
        reasons.append("BROOKS_PRICE_NOT_STABLE")
    if not result.volume_dry_pass:
        reasons.append("BROOKS_VOLUME_NOT_DRY")
    if not result.support_not_broken:
        reasons.append("BROOKS_SUPPORT_BROKEN")
    if not result.setup_pass:
        reasons.append("BROOKS_SETUP_NOT_FOUND")
    if compact.structure_type == "COMPACT_BEARISH":
        reasons.append("BROOKS_COMPACT_BEARISH")
    return reasons
