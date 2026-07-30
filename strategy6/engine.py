"""Strategy6 single-stock evaluation entry point."""
from __future__ import annotations

from strategy6.dry_tail import evaluate_dry_tail
from strategy6.entry import identify_entry_archetype
from strategy6.entry_quality import (
    evaluate_entry_timing,
    evaluate_probability_adjusted_rr,
)
from strategy6.box_tail import combine_tail_paths, evaluate_box_tail, evaluate_compact_kline
from strategy6.brooks.tail import analyze_brooks_tail
from strategy6.brooks.models import BrooksTailResult
from strategy6.brooks.trigger import evaluate_brooks_trade_trigger
from strategy6.filters import (
    classify_candidate,
    classify_candidate_before_market_downgrade,
    hard_filter_reasons,
)
from strategy6.indicators import _atr, calculate_indicators
from strategy6.market import compute_relative_strength_20, evaluate_market_context, has_relative_strength_20_market
from strategy6.models import (
    Strategy6BoxTail,
    Strategy6Evaluation,
    Strategy6ProbabilityAdjustedRR,
    Strategy6TailRegime,
)
from strategy6.phase import segment_phases
from strategy6.pattern import detect_pattern
from strategy6.pressure import apply_pressure_tags
from strategy6.scorer import score_strategy6
from strategy6.selection_diagnostics import evaluate_selection_diagnostics
from strategy6.setup_quality import evaluate_setup_quality
from strategy6.strong_start import evaluate_strong_start
from strategy6.support import evaluate_support
from strategy6.tail_regime import evaluate_tail_regime
from strategy6.ttm_squeeze import calculate_ttm_squeeze
from strategy6.trade_plan import calculate_trade_plan
from strategy6.validation import (
    is_strategy6_research_profile,
    resolve_strategy6_config,
    strategy6_config_hash,
)
from strategy6.version import STRATEGY6_VERSION
from strategy6.vcp_observer import apply_vcp_base_filters, evaluate_vcp_observation


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
        ttm_squeeze = calculate_ttm_squeeze(rows, self.config["ttm_squeeze"])
        vcp_observation = evaluate_vcp_observation(rows, self.config, code=code)
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
        previous_consolidation_start_index = None
        previous_key_support_price = None
        previous_phase_valid = False
        if self.config["tail_regime_shadow_enabled"] and phase.valid and len(rows) > 1:
            previous_rows, previous_indicators = calculate_indicators(
                rows[:-1],
                self.config,
                trading_days_override=(
                    max(0, trading_days_override - 1)
                    if trading_days_override is not None else None
                ),
                rows_normalized=True,
            )
            previous_start = evaluate_strong_start(
                previous_rows,
                previous_indicators,
                self.config,
                code,
            )
            previous_phase = segment_phases(previous_rows, previous_start, self.config)
            previous_phase_valid = previous_phase.valid
            previous_consolidation_start_index = previous_phase.consolidation_start_index
            previous_pattern = detect_pattern(previous_rows, previous_phase, self.config)
            previous_support = evaluate_support(
                previous_rows,
                previous_indicators,
                previous_start,
                previous_pattern,
                self.config,
            )
            previous_key_support_price = previous_support.key_support_price
        if self.config["tail_regime_shadow_enabled"] and not phase.valid:
            tail_regime = Strategy6TailRegime(
                status="INSUFFICIENT_BASELINE",
                risks=[phase.status],
            )
        else:
            tail_regime = evaluate_tail_regime(
                rows,
                consolidation_start_index=phase.consolidation_start_index,
                previous_consolidation_start_index=previous_consolidation_start_index,
                enabled=self.config["tail_regime_shadow_enabled"],
                big_down_return=self.config["big_down_return"],
                big_down_volume_ratio=self.config["big_down_volume_ratio"],
                key_support_price=support.key_support_price,
                previous_key_support_price=previous_key_support_price,
                previous_phase_valid=previous_phase_valid,
            )
        setup_quality = evaluate_setup_quality(
            rows,
            start,
            phase,
            market_data_by_symbol,
        )
        dry_tail = evaluate_dry_tail(rows, indicators, phase, self.config)
        research_profile = is_strategy6_research_profile(self.config)
        if research_profile:
            box_tail = evaluate_box_tail(
                rows,
                has_volume_selloff=indicators.has_big_down_volume,
                phase=phase,
                support=support,
                original_tail=dry_tail,
                config=self.config["box_tail"],
            )
            brooks_compact = box_tail.compact_kline
            if not brooks_compact.enabled:
                compact_config = dict(self.config["box_tail"]["compact_kline"])
                compact_config["enabled"] = True
                brooks_compact = evaluate_compact_kline(
                    rows,
                    atr5=_atr(rows, 5),
                    atr20=_atr(rows, 20),
                    tail_volume_ratio=dry_tail.tail_volume_ratio,
                    premium_tail_volume_ratio_max=self.config["brooks_tail"]["volume_dry"]["premium_tail_volume_ratio_max"],
                    has_volume_selloff=indicators.has_big_down_volume,
                    config=compact_config,
                )
            brooks_tail = analyze_brooks_tail(
                rows,
                indicators,
                start,
                phase,
                support,
                dry_tail,
                brooks_compact,
                config=self.config["brooks_tail"],
            )
            brooks_tail.trade_trigger = evaluate_brooks_trade_trigger(
                rows,
                brooks_tail,
                support,
                start_grade=start.start_grade,
                atr14=indicators.atr14,
                config=self.config["brooks_tail"],
            )
            if brooks_tail.trade_trigger.ready:
                brooks_tail.status = brooks_tail.trade_trigger.trigger_type
        else:
            box_tail = Strategy6BoxTail(status="DISABLED_FORMAL_PROFILE")
            brooks_tail = BrooksTailResult.disabled()
        tail_paths = combine_tail_paths(dry_tail, box_tail, brooks_tail)
        apply_pressure_tags(rows, indicators)
        entry_archetype = identify_entry_archetype(
            rows,
            indicators,
            support,
            brooks_tail,
            self.config,
        )
        trade_plan = calculate_trade_plan(
            indicators,
            support,
            self.config,
            entry_archetype=entry_archetype,
            entry_trigger_price=brooks_tail.trade_trigger.trigger_price,
        )
        entry_timing = evaluate_entry_timing(
            rows,
            indicators,
            support,
            entry_archetype=entry_archetype,
        )
        selection_diagnostics = evaluate_selection_diagnostics(
            rows,
            code=code,
            support=support,
            tail_regime=tail_regime,
            trade_plan=trade_plan,
            setup_quality=setup_quality,
            market_data_by_symbol=market_data_by_symbol,
            expected_trade_date=indicators.evaluation_date,
        )
        score = score_strategy6(
            indicators, start, phase, pattern, support, dry_tail, trade_plan, self.config,
            box_tail=box_tail,
            brooks_tail=brooks_tail,
            setup_quality=setup_quality,
        )
        ranking_score = score.total_score + ttm_squeeze.score
        reject_reasons = hard_filter_reasons(
            rows, indicators, start, phase, pattern, support, dry_tail, trade_plan, self.config,
            box_tail=box_tail,
            brooks_tail=brooks_tail,
            setup_quality=setup_quality,
            selection_diagnostics=selection_diagnostics,
        )
        normalized_quote_status = str(quote_status or "").lower()
        if normalized_quote_status == "suspended":
            reject_reasons.append("LATEST_TRADE_SUSPENDED")
        elif normalized_quote_status == "no_trade":
            reject_reasons.append("LATEST_TRADE_NO_TRADE")
        apply_vcp_base_filters(vcp_observation, reject_reasons)
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
            box_tail=box_tail,
            brooks_tail=brooks_tail,
            selection_diagnostics=selection_diagnostics,
        )
        probability_rr = Strategy6ProbabilityAdjustedRR()
        if candidate_type != "REJECTED":
            probability_config = self.config["entry_quality"]
            probability_rr = evaluate_probability_adjusted_rr(
                rows,
                indicators,
                trade_plan,
                lookback_days=probability_config["probability_lookback_days"],
                horizon_days=probability_config["probability_horizon_days"],
                minimum_samples=probability_config["probability_minimum_samples"],
            )
        if (
            self.config["entry_quality"]["entry_timing_enabled"]
            or self.config["entry_quality"]["probability_rr_enabled"]
        ):
            reject_reasons = hard_filter_reasons(
                rows,
                indicators,
                start,
                phase,
                pattern,
                support,
                dry_tail,
                trade_plan,
                self.config,
                box_tail=box_tail,
                brooks_tail=brooks_tail,
                setup_quality=setup_quality,
                selection_diagnostics=selection_diagnostics,
                entry_timing=entry_timing,
                probability_rr=probability_rr,
            )
            if normalized_quote_status == "suspended":
                reject_reasons.append("LATEST_TRADE_SUSPENDED")
            elif normalized_quote_status == "no_trade":
                reject_reasons.append("LATEST_TRADE_NO_TRADE")
            apply_vcp_base_filters(vcp_observation, reject_reasons)
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
                box_tail=box_tail,
                brooks_tail=brooks_tail,
                selection_diagnostics=selection_diagnostics,
                entry_timing=entry_timing,
                probability_rr=probability_rr,
            )
        pre_market_candidate_type = ""
        if (
            candidate_type == "WATCH_CANDIDATE"
            and indicators.market_filter_enabled
            and indicators.market_filter_mode == "downgrade"
            and indicators.market_status in {"MARKET_WEAK", "MARKET_RISK"}
        ):
            audited_type = classify_candidate_before_market_downgrade(
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
                box_tail=box_tail,
                brooks_tail=brooks_tail,
                selection_diagnostics=selection_diagnostics,
                entry_timing=entry_timing,
                probability_rr=probability_rr,
            )
            if audited_type in {"READY_CANDIDATE", "KEY_CANDIDATE"}:
                pre_market_candidate_type = audited_type
            else:
                indicators.warn_tags = [
                    tag for tag in indicators.warn_tags
                    if tag != "MARKET_WEAK_DOWNGRADED"
                ]
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
            box_tail=box_tail,
            brooks_tail=brooks_tail,
            tail_paths=tail_paths,
            trade_plan=trade_plan,
            score=score,
            ttm_squeeze=ttm_squeeze,
            ranking_score=ranking_score,
            setup_quality=setup_quality,
            tail_regime=tail_regime,
            selection_diagnostics=selection_diagnostics,
            entry_timing=entry_timing,
            probability_rr=probability_rr,
            vcp_observation=vcp_observation,
            strategy_version=STRATEGY6_VERSION,
            config_hash=strategy6_config_hash(self.config),
            decision_profile=self.config["decision_profile"],
            pre_market_candidate_type=pre_market_candidate_type,
            candidate_type=candidate_type,
            classification=classification,
            lifecycle_status=lifecycle_status,
            reject_reasons=reject_reasons,
            suggestion=suggestion,
            data_source=data_source,
            kline_fetched_at=kline_fetched_at,
            quote_status=quote_status,
        )
