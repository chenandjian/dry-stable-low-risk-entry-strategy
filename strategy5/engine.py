"""Strategy5 single-stock evaluation entry point."""
from __future__ import annotations

from strategy5.filters import classify_candidate, hard_filter_reasons
from strategy5.indicators import calculate_indicators
from strategy5.models import Strategy5Evaluation, Strategy5Score, Strategy5Support
from strategy5.scorer import score_strategy5
from strategy5.support import evaluate_support_status
from strategy5.validation import resolve_strategy5_config


class ShortSprintSupportEngine:
    """Evaluate short-term sprint support quality for Strategy5."""

    def __init__(self, config: dict | None = None):
        self.config = resolve_strategy5_config(config or {})

    def evaluate_at(
        self,
        data: list[dict],
        *,
        code: str,
        name: str = "",
        data_source: str = "",
        kline_fetched_at: str = "",
        quote_status: str = "",
        trading_days_override: int | None = None,
        rows_normalized: bool = False,
    ) -> Strategy5Evaluation:
        indicators = calculate_indicators(
            data,
            self.config,
            trading_days_override=trading_days_override,
            rows_normalized=rows_normalized,
        )
        if indicators.trading_days < self.config["minimum_kline_days"]:
            support = Strategy5Support("SPRINT_FAILED")
            score = Strategy5Score()
            reasons = ["INSUFFICIENT_KLINE_DAYS"]
            return Strategy5Evaluation(
                code=code,
                name=name,
                indicators=indicators,
                support=support,
                score=score,
                reject_reasons=reasons,
                status_reason=reasons[0],
                data_source=data_source,
                kline_latest_date=indicators.evaluation_date,
                kline_fetched_at=kline_fetched_at,
                quote_status=quote_status,
            )

        support = evaluate_support_status(
            close=indicators.close,
            ma5=indicators.ma5,
            ma10=indicators.ma10,
            ma20=indicators.ma20,
            ma50=indicators.ma50,
        )
        reject_reasons = hard_filter_reasons(indicators, self.config)
        candidate_type, classification = classify_candidate(indicators, support, self.config, reject_reasons)
        score = score_strategy5(indicators, support)
        status_reason = reject_reasons[0] if reject_reasons else candidate_type
        return Strategy5Evaluation(
            code=code,
            name=name,
            indicators=indicators,
            support=support,
            score=score,
            candidate_type=candidate_type,
            classification=classification,
            reject_reasons=reject_reasons,
            status_reason=status_reason,
            data_source=data_source,
            kline_latest_date=indicators.evaluation_date,
            kline_fetched_at=kline_fetched_at,
            quote_status=quote_status,
        )
