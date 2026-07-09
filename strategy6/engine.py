"""Strategy6 single-stock evaluation entry point."""
from __future__ import annotations

from strategy6.dry_tail import evaluate_dry_tail
from strategy6.filters import classify_candidate, hard_filter_reasons
from strategy6.indicators import calculate_indicators
from strategy6.models import Strategy6Evaluation
from strategy6.pressure import apply_pressure_tags
from strategy6.scorer import score_strategy6
from strategy6.strong_start import evaluate_strong_start
from strategy6.support import evaluate_support
from strategy6.trade_plan import calculate_trade_plan
from strategy6.validation import resolve_strategy6_config


class StrongVcpTailEngine:
    """Evaluate strong-start VCP/Cup-handle tail candidates."""

    def __init__(self, config: dict | None = None):
        self.config = resolve_strategy6_config(config or {})

    def evaluate_at(
        self,
        data: list[dict],
        *,
        code: str,
        name: str = "",
        sector_name: str = "",
        data_source: str = "",
        kline_fetched_at: str = "",
        quote_status: str = "",
        trading_days_override: int | None = None,
        rows_normalized: bool = False,
    ) -> Strategy6Evaluation:
        rows, indicators = calculate_indicators(
            data,
            self.config,
            trading_days_override=trading_days_override,
            rows_normalized=rows_normalized,
        )
        start = evaluate_strong_start(rows, indicators, self.config, code)
        support = evaluate_support(rows, indicators, start)
        dry_tail = evaluate_dry_tail(rows, indicators, self.config)
        apply_pressure_tags(rows, indicators)
        trade_plan = calculate_trade_plan(indicators, support)
        score = score_strategy6(indicators, start, support, dry_tail, trade_plan)
        reject_reasons = hard_filter_reasons(indicators, start, support, dry_tail, trade_plan, self.config)
        candidate_type, classification, lifecycle_status, suggestion = classify_candidate(
            indicators,
            start,
            support,
            dry_tail,
            trade_plan,
            score,
            reject_reasons,
            self.config,
        )
        return Strategy6Evaluation(
            code=code,
            name=name,
            sector_name=sector_name,
            indicators=indicators,
            start=start,
            support=support,
            dry_tail=dry_tail,
            trade_plan=trade_plan,
            score=score,
            candidate_type=candidate_type,
            classification=classification,
            lifecycle_status=lifecycle_status,
            reject_reasons=reject_reasons,
            suggestion=suggestion,
            data_source=data_source,
            kline_fetched_at=kline_fetched_at,
            quote_status=quote_status,
        )

