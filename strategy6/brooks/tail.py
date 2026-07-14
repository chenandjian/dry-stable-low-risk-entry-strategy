"""Brooks tail-path scoring and final candidate decision."""
from __future__ import annotations

from strategy6.brooks.models import (
    BrooksCompactStructureResult,
    BrooksContextResult,
    BrooksSellingPressureResult,
    BrooksStructureResult,
    BrooksTailResult,
)


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
