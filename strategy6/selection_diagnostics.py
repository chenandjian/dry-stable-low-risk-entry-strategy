"""Selection facts that do not alter Strategy6 candidate decisions."""
from __future__ import annotations

from strategy6.market import (
    compute_relative_strength_periods,
    evaluate_single_index_context,
)
from strategy6.models import (
    Strategy6SelectionDiagnostics,
    Strategy6SetupQuality,
    Strategy6Support,
    Strategy6TailRegime,
    Strategy6TradePlan,
)


def evaluate_selection_diagnostics(
    rows: list[dict],
    *,
    code: str,
    support: Strategy6Support,
    tail_regime: Strategy6TailRegime,
    trade_plan: Strategy6TradePlan,
    setup_quality: Strategy6SetupQuality,
    market_data_by_symbol: dict[str, list[dict]] | None,
    expected_trade_date: str = "",
) -> Strategy6SelectionDiagnostics:
    matched_symbol = _matched_market_symbol(code)
    periods = compute_relative_strength_periods(
        rows,
        market_data_by_symbol,
        expected_trade_date=expected_trade_date,
    )
    support_status = _support_confirmation_status(support)
    tail_status = _recent_tail_status(tail_regime)
    reasons = [
        f"SUPPORT_CONFIRMATION_{support_status}",
        f"RECENT_TAIL_{tail_status}",
    ]
    risks = list(support.support_reaction_risk_tags) + list(tail_regime.risks)
    return Strategy6SelectionDiagnostics(
        relative_strength_5=(periods or {}).get(5, 0.0),
        relative_strength_10=(periods or {}).get(10, 0.0),
        relative_strength_20=(periods or {}).get(20, 0.0),
        relative_strength_60=(periods or {}).get(60, 0.0),
        relative_strength_periods_observed=sorted((periods or {}).keys()),
        relative_strength_trend=setup_quality.relative_strength_trend,
        matched_market_symbol=matched_symbol,
        matched_market_status=evaluate_single_index_context(
            matched_symbol,
            market_data_by_symbol,
            expected_trade_date=expected_trade_date,
        ),
        support_confirmation_status=support_status,
        recent_tail_status=tail_status,
        conservative_rr=trade_plan.objective_rr_1,
        reasons=reasons,
        risk_tags=_dedupe(risks),
    )


def _matched_market_symbol(code: str) -> str:
    normalized = str(code or "").strip()
    if normalized.startswith(("300", "301")):
        return "sz399006"
    if normalized.startswith(("000", "001", "002", "003")):
        return "sz399001"
    return "sh000001"


def _support_confirmation_status(support: Strategy6Support) -> str:
    if support.support_status == "SUPPORT_FAILED" or "SUPPORT_VOLUME_BREAK_UNRECOVERED" in support.support_reaction_risk_tags:
        return "FAILED"
    if support.support_reaction_score >= 5 and not support.support_reaction_risk_tags:
        return "CONFIRMED"
    if support.support_reaction_score >= 3:
        return "PARTIAL"
    return "PENDING"


def _recent_tail_status(tail_regime: Strategy6TailRegime) -> str:
    if tail_regime.status == "BROKEN" or any(
        risk in {
            "TAIL_REGIME_BIG_DOWN_VOLUME",
            "TAIL_REGIME_LOW_DETERIORATING",
            "SUPPORT_TWO_CLOSE_BREAK",
        }
        for risk in tail_regime.risks
    ):
        return "DETERIORATING"
    if tail_regime.status == "CONFIRMED":
        return "STABLE"
    if tail_regime.status in {"FORMING", "NO_REGIME_CHANGE"}:
        return "FORMING"
    return "UNKNOWN"


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
