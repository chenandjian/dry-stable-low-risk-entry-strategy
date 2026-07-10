"""Strategy6 single-stock evaluation entry point."""
from __future__ import annotations

from strategy6.dry_tail import evaluate_dry_tail
from strategy6.filters import classify_candidate, hard_filter_reasons
from strategy6.indicators import calculate_indicators
from strategy6.market import compute_relative_strength_20, evaluate_market_context, has_relative_strength_20_market
from strategy6.models import Strategy6Evaluation
from strategy6.phase import segment_phases
from strategy6.pattern import detect_pattern
from strategy6.pressure import apply_pressure_tags
from strategy6.scorer import score_strategy6
from strategy6.strong_start import evaluate_strong_start
from strategy6.support import evaluate_support
from strategy6.trade_plan import calculate_trade_plan
from strategy6.validation import resolve_strategy6_config, strategy6_config_hash
from strategy6.version import STRATEGY6_VERSION


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
        market_data_by_symbol: dict[str, list[dict]] | None = None,
    ) -> Strategy6Evaluation:
        rows, indicators = calculate_indicators(
            data,
            self.config,
            trading_days_override=trading_days_override,
            rows_normalized=rows_normalized,
        )
        market_context = evaluate_market_context(
            market_data_by_symbol,
            expected_trade_date=indicators.evaluation_date,
        )
        indicators.market_status = market_context["market_status"]
        indicators.relative_strength_20_observed = has_relative_strength_20_market(
            market_data_by_symbol,
            expected_trade_date=indicators.evaluation_date,
        )
        indicators.relative_strength_20 = compute_relative_strength_20(
            indicators.return_20,
            market_data_by_symbol,
            expected_trade_date=indicators.evaluation_date,
        )
        indicators.market_filter_enabled = bool(self.config["enable_market_filter"])
        indicators.market_filter_mode = self.config["market_filter_mode"]
        start = evaluate_strong_start(rows, indicators, self.config, code)
        phase = segment_phases(rows, start, self.config)
        pattern = detect_pattern(rows, phase, self.config)
        support = evaluate_support(rows, indicators, start, pattern, self.config)
        dry_tail = evaluate_dry_tail(rows, indicators, phase, self.config)
        apply_pressure_tags(rows, indicators)
        trade_plan = calculate_trade_plan(indicators, support, self.config)
        score = score_strategy6(indicators, start, phase, pattern, support, dry_tail, trade_plan, self.config)
        reject_reasons = hard_filter_reasons(
            rows, indicators, start, phase, pattern, support, dry_tail, trade_plan, self.config
        )
        normalized_quote_status = str(quote_status or "").lower()
        if normalized_quote_status == "suspended":
            reject_reasons.append("LATEST_TRADE_SUSPENDED")
        elif normalized_quote_status == "no_trade":
            reject_reasons.append("LATEST_TRADE_NO_TRADE")
        candidate_type, classification, lifecycle_status, suggestion = classify_candidate(
            indicators,
            start,
            phase,
            pattern,
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
            phase=phase,
            pattern=pattern,
            support=support,
            dry_tail=dry_tail,
            trade_plan=trade_plan,
            score=score,
            strategy_version=STRATEGY6_VERSION,
            config_hash=strategy6_config_hash(self.config),
            candidate_type=candidate_type,
            classification=classification,
            lifecycle_status=lifecycle_status,
            reject_reasons=reject_reasons,
            suggestion=suggestion,
            data_source=data_source,
            kline_fetched_at=kline_fetched_at,
            quote_status=quote_status,
        )
