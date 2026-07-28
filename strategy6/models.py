"""Strategy6 data models."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Strategy6Indicators:
    evaluation_date: str = ""
    current_price: float = 0.0
    daily_return: float = 0.0
    current_close_position: float = 0.0
    trading_days: int = 0
    ma5: float = 0.0
    ma10: float = 0.0
    ma20: float = 0.0
    ma50: float = 0.0
    ma120: float = 0.0
    ma250: float = 0.0
    atr14: float = 0.0
    return_5: float = 0.0
    return_10: float = 0.0
    return_20: float = 0.0
    amount_avg_10: float = 0.0
    amount_avg_30: float = 0.0
    amount_avg_60: float = 0.0
    v3: float = 0.0
    v5: float = 0.0
    v10: float = 0.0
    v20: float = 0.0
    volume_ratio_5_20: float = 0.0
    current_volume_ratio_20: float = 0.0
    highest_close_20: float = 0.0
    highest_close_120: float = 0.0
    highest_close_250: float = 0.0
    pullback_from_20d_high: float = 0.0
    range_5: float = 0.0
    range_10: float = 0.0
    close_range_5: float = 0.0
    consecutive_down_days: int = 0
    consecutive_down_low: float | None = None
    consecutive_down_structure_version: str = "CONSECUTIVE_DOWN_INTERVAL_5D_V2"
    consecutive_down_structure_pass: bool = False
    consecutive_down_no_new_streak_low: bool | None = None
    consecutive_down_min_low_margin_pct: float | None = None
    consecutive_down_max_high_break_pct: float | None = None
    relative_strength_20: float = 0.0
    relative_strength_20_observed: bool = False
    market_status: str = "UNKNOWN"
    market_filter_enabled: bool = False
    market_filter_mode: str = "downgrade"
    has_big_down_volume: bool = False
    risk_tags: list[str] = field(default_factory=list)
    warn_tags: list[str] = field(default_factory=list)


@dataclass
class Strategy6Start:
    start_date: str = ""
    start_type: str = "NONE"
    start_grade: str = "NONE"
    start_day_return: float = 0.0
    start_day_volume_ratio: float = 0.0
    start_day_amount: float = 0.0
    start_day_close_position: float = 0.0
    start_day_self_amount_percentile: float = 0.0
    start_low: float = 0.0
    is_limit_up: bool = False
    is_one_word_limit_up: bool = False
    limit_up_pct: float = 0.0
    high_trigger: str = ""
    days_since_start: int = 0
    event_quality_score: int = 0
    follow_through_return_5: float = 0.0
    gain_retention_ratio: float = 0.0
    max_close_drawdown_5: float = 0.0
    failure_reasons: list[str] = field(default_factory=list)


@dataclass
class Strategy6Phase:
    status: str = "START_NOT_FOUND"
    valid: bool = False
    lifecycle_status: str = "SETUP_FORMING"
    start_index: int = -1
    consolidation_start_index: int = -1
    tail_start_index: int = -1
    signal_index: int = -1
    start_date: str = ""
    consolidation_start_date: str = ""
    tail_start_date: str = ""
    signal_date: str = ""
    start_age_days: int = 0
    consolidation_days: int = 0
    tail_days: int = 0
    tail_segmentation_status: str = "FIXED_WINDOW"
    tail_segmentation_score: int = 0
    tail_range_contraction_ratio: float = 0.0
    tail_atr_contraction_ratio: float = 0.0
    tail_body_contraction_ratio: float = 0.0


@dataclass
class Strategy6Pattern:
    pattern_type: str = "UNKNOWN"
    pattern_score: int = 0
    pattern_start_date: str = ""
    pattern_end_date: str = ""
    pivot_source: str = ""
    pivot_price: float = 0.0
    pattern_low: float = 0.0
    pattern_height: float = 0.0
    depth_pct: float = 0.0
    contraction_count: int = 0
    reasons: list[str] = field(default_factory=list)


@dataclass
class Strategy6Support:
    support_status: str = "SUPPORT_FAILED"
    main_support_ma: str = ""
    key_support_price: float = 0.0
    tactical_support_price: float = 0.0
    prior_key_support_price: float = 0.0
    support_zone_low: float = 0.0
    support_zone_high: float = 0.0
    defense_support_price: float = 0.0
    support_test_count: int = 0
    pivot_price: float = 0.0
    box_height: float = 0.0
    support_score: int = 0
    support_cluster_sources: list[str] = field(default_factory=list)
    support_cluster_score: int = 0
    support_reaction_score: int = 0
    support_reaction_reasons: list[str] = field(default_factory=list)
    support_reaction_risk_tags: list[str] = field(default_factory=list)


@dataclass
class Strategy6SetupQuality:
    score: int = 0
    gain_retention_ratio: float = 0.0
    distribution_day_count: int = 0
    up_down_volume_ratio: float = 0.0
    volatility_contraction_ratio: float = 0.0
    failed_breakout_count: int = 0
    relative_strength_trend: str = "UNKNOWN"
    reasons: list[str] = field(default_factory=list)
    risk_tags: list[str] = field(default_factory=list)


@dataclass
class Strategy6DryTail:
    dry_stable_score: int = 0
    dry_tail_pass: bool = False
    reasons: list[str] = field(default_factory=list)
    rejects: list[str] = field(default_factory=list)
    tail_avg_volume: float = 0.0
    pre_tail_avg_volume_20: float = 0.0
    tail_volume_ratio: float = 0.0
    volume_slope_10: float = 0.0


@dataclass
class Strategy6TailRegime:
    enabled: bool = True
    status: str = "INSUFFICIENT_BASELINE"
    start_date: str = ""
    days: int = 0
    delta_bic: float = 0.0
    volume_ratio: float = 0.0
    range_ratio: float = 0.0
    body_ratio: float = 0.0
    abs_return_ratio: float = 0.0
    close_dispersion: float = 0.0
    low_slope_atr: float = 0.0
    model_version: str = "TAIL_REGIME_CP_V1"
    reasons: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)


@dataclass
class Strategy6CompactKline:
    enabled: bool = False
    passed: bool = False
    premium: bool = False
    score: int = 0
    quality_tag: str = "NONE"
    avg_body_ratio: float | None = None
    max_body_ratio: float | None = None
    close_range: float | None = None
    overlap_pair_count: int = 0
    premium_overlap_pair_count: int = 0
    valid_overlap_pair_count: int = 0
    avg_overlap_ratio: float | None = None
    gap_count: int = 0
    max_gap_ratio: float | None = None
    atr5: float | None = None
    atr20: float | None = None
    atr_contraction_ratio: float | None = None
    reasons: list[str] = field(default_factory=list)
    risk_tags: list[str] = field(default_factory=list)


@dataclass
class Strategy6BoxTail:
    enabled: bool = False
    passed: bool = False
    score: int = 0
    status: str = "NO_BOX"
    start_date: str = ""
    end_date: str = ""
    days: int = 0
    box_high: float | None = None
    box_low: float | None = None
    box_width: float | None = None
    box_position: float | None = None
    box_position_raw: float | None = None
    low_test_count: int = 0
    high_test_count: int = 0
    first_half_volume: float | None = None
    second_half_volume: float | None = None
    volume_contraction_ratio: float | None = None
    first_half_median_close: float | None = None
    second_half_median_close: float | None = None
    center_shift: float | None = None
    break_reason: str = ""
    selection_reason: str = ""
    compact_kline: Strategy6CompactKline = field(default_factory=Strategy6CompactKline)
    quality_score: int = 0
    quality_tag: str = "NONE"
    reasons: list[str] = field(default_factory=list)
    risk_tags: list[str] = field(default_factory=list)


@dataclass
class Strategy6TailPaths:
    original_pass: bool = False
    original_score: int = 0
    box_pass: bool = False
    box_score: int = 0
    brooks_pass: bool = False
    brooks_score: int = 0
    passed: bool = False
    path: str = "NONE"
    paths: list[str] = field(default_factory=list)
    summary: str = "NONE"
    primary: str = "NONE"
    passed_path_count: int = 0
    multi_path_confirmed: bool = False
    score: int = 0


@dataclass
class Strategy6TradePlan:
    suggested_buy_price: float | None = None
    buy_zone_low: float = 0.0
    buy_zone_high: float = 0.0
    stop_loss_price: float = 0.0
    target_price_1: float = 0.0
    target_price_2: float = 0.0
    target_price_3: float = 0.0
    objective_target_1: float = 0.0
    objective_target_2: float = 0.0
    execution_target_1_5r: float = 0.0
    execution_target_2r: float = 0.0
    execution_target_2_5r: float = 0.0
    execution_target_3_5r: float = 0.0
    risk_amount: float = 0.0
    reward_amount_1: float = 0.0
    reward_amount_2: float = 0.0
    reward_amount_3: float = 0.0
    risk_reward_ratio_1: float = 0.0
    risk_reward_ratio_2: float = 0.0
    risk_reward_ratio_3: float = 0.0
    objective_rr_1: float = 0.0
    objective_rr_2: float = 0.0
    signal_date: str = ""
    valid_from_date: str = ""
    valid_until_date: str = ""
    buy_zone_valid_days: int = 0
    suggested_limit_price: float | None = None
    execution_notes: list[str] = field(default_factory=list)
    entry_archetype: str = "NONE"


@dataclass
class Strategy6Score:
    strong_start_score: int = 0
    support_score: int = 0
    dry_stable_score: int = 0
    risk_reward_score: int = 0
    risk_control_score: int = 0
    total_score: int = 0
    score_reasons: list[str] = field(default_factory=list)
    pattern_score_component: int = 0
    tail_score: int = 0
    objective_rr_score: int = 0
    relative_strength_risk_score: int = 0
    setup_quality_score: int = 0
    support_reaction_score: int = 0
    path_evidence_score: int = 0
    score_model_version: str = ""


@dataclass
class Strategy6TtmSqueeze:
    status: str = "INSUFFICIENT_DATA"
    squeeze_on: bool = False
    squeeze_days: int = 0
    fired: bool = False
    momentum: float | None = None
    previous_momentum: float | None = None
    momentum_direction: str = "UNKNOWN"
    bb_upper: float | None = None
    bb_lower: float | None = None
    kc_upper: float | None = None
    kc_lower: float | None = None
    score: int = 0
    reasons: list[str] = field(default_factory=list)
    risk_tags: list[str] = field(default_factory=list)
    model_version: str = "S6_TTM_SQUEEZE_V1"


@dataclass
class Strategy6VcpQuality:
    scored: bool = False
    score: int | None = None
    grade: str = ""
    contraction_score: int = 0
    range_score: int = 0
    volume_score: int = 0
    low_score: int = 0
    start_retention_score: int = 0
    time_score: int = 0
    pivot_score: int = 0
    breakout_score: int = 0
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    model_version: str = ""


@dataclass
class Strategy6VcpObservation:
    eligible: bool = False
    lifecycle_status: str = "VCP_NONE"
    origin_start_date: str = ""
    pattern_start_date: str = ""
    pattern_end_date: str = ""
    contraction_count: int = 0
    contractions: list[dict] = field(default_factory=list)
    forming_round: dict = field(default_factory=dict)
    pivot_price: float = 0.0
    structure_low: float = 0.0
    distance_to_pivot_pct: float = 0.0
    breakout_date: str = ""
    days_since_breakout: int = 0
    reasons: list[str] = field(default_factory=list)
    risk_tags: list[str] = field(default_factory=list)
    invalidation_reason: str = ""
    history_qualified: bool = False
    history_candidate_date: str = ""
    history_candidate_type: str = ""
    history_candidate_score: int = 0
    history_source: str = ""
    history_origin_start_date: str = ""
    quality: Strategy6VcpQuality = field(default_factory=Strategy6VcpQuality)


@dataclass
class Strategy6Evaluation:
    code: str
    name: str
    sector_name: str
    indicators: Strategy6Indicators
    start: Strategy6Start
    phase: Strategy6Phase
    pattern: Strategy6Pattern
    support: Strategy6Support
    dry_tail: Strategy6DryTail
    box_tail: Strategy6BoxTail
    brooks_tail: object
    tail_paths: Strategy6TailPaths
    trade_plan: Strategy6TradePlan
    score: Strategy6Score
    setup_quality: Strategy6SetupQuality = field(default_factory=Strategy6SetupQuality)
    tail_regime: Strategy6TailRegime = field(default_factory=Strategy6TailRegime)
    vcp_observation: Strategy6VcpObservation = field(default_factory=Strategy6VcpObservation)
    strategy_version: str = ""
    config_hash: str = ""
    decision_profile: str = "formal_original"
    pre_market_candidate_type: str = ""
    candidate_type: str = "REJECTED"
    classification: str = "rejected"
    lifecycle_status: str = "FAILED"
    reject_reasons: list[str] = field(default_factory=list)
    suggestion: str = ""
    data_source: str = ""
    kline_fetched_at: str = ""
    quote_status: str = ""

    @property
    def passed(self) -> bool:
        return self.candidate_type in {"READY_CANDIDATE", "KEY_CANDIDATE", "WATCH_CANDIDATE"}

    def to_candidate_dict(self) -> dict:
        ind = self.indicators
        start = self.start
        support = self.support
        plan = self.trade_plan
        score = self.score
        box = self.box_tail
        brooks = self.brooks_tail
        compact = box.compact_kline
        tail = self.tail_paths
        quality = self.setup_quality
        regime = self.tail_regime
        vcp = self.vcp_observation
        vcp_quality = vcp.quality
        return {
            "strategy_version": self.strategy_version,
            "config_hash": self.config_hash,
            "decision_profile": self.decision_profile,
            "price_basis": "FORWARD_ADJUSTED",
            "current_price_adj": ind.current_price,
            "current_price_raw": None,
            "code": self.code,
            "name": self.name,
            "sector_name": self.sector_name,
            "evaluation_date": ind.evaluation_date,
            "current_price": ind.current_price,
            "close": ind.current_price,
            "daily_return": ind.daily_return,
            "current_close_position": ind.current_close_position,
            "trading_days": ind.trading_days,
            "ma5": ind.ma5,
            "ma10": ind.ma10,
            "ma20": ind.ma20,
            "ma50": ind.ma50,
            "ma120": ind.ma120,
            "ma250": ind.ma250,
            "atr14": ind.atr14,
            "return_5": ind.return_5,
            "return_10": ind.return_10,
            "return_20": ind.return_20,
            "relative_strength_20": ind.relative_strength_20,
            "relative_strength_20_observed": ind.relative_strength_20_observed,
            "amount_avg_10": ind.amount_avg_10,
            "amount_avg_30": ind.amount_avg_30,
            "amount_avg_60": ind.amount_avg_60,
            "v3": ind.v3,
            "v5": ind.v5,
            "v10": ind.v10,
            "v20": ind.v20,
            "volume_ratio_5_20": ind.volume_ratio_5_20,
            "current_volume_ratio_20": ind.current_volume_ratio_20,
            "tail_avg_volume": self.dry_tail.tail_avg_volume,
            "pre_tail_avg_volume_20": self.dry_tail.pre_tail_avg_volume_20,
            "tail_volume_ratio": self.dry_tail.tail_volume_ratio,
            "volume_slope_10": self.dry_tail.volume_slope_10,
            "tail_regime_enabled": regime.enabled,
            "tail_regime_status": regime.status,
            "tail_regime_start_date": regime.start_date,
            "tail_regime_days": regime.days,
            "tail_regime_delta_bic": regime.delta_bic,
            "tail_regime_volume_ratio": regime.volume_ratio,
            "tail_regime_range_ratio": regime.range_ratio,
            "tail_regime_body_ratio": regime.body_ratio,
            "tail_regime_abs_return_ratio": regime.abs_return_ratio,
            "tail_regime_close_dispersion": regime.close_dispersion,
            "tail_regime_low_slope_atr": regime.low_slope_atr,
            "tail_regime_model_version": regime.model_version,
            "tail_regime_reasons": regime.reasons,
            "tail_regime_risks": regime.risks,
            "original_tail_pass": tail.original_pass,
            "original_tail_score": tail.original_score,
            "box_tail_enabled": box.enabled,
            "box_tail_pass": tail.box_pass,
            "box_tail_score": tail.box_score,
            "box_status": box.status,
            "tail_pass": tail.passed,
            "tail_path": tail.path,
            "tail_paths": tail.paths,
            "tail_path_summary": tail.summary,
            "tail_primary_path": tail.primary,
            "passed_path_count": tail.passed_path_count,
            "multi_path_confirmed": tail.multi_path_confirmed,
            "box_start_date": box.start_date,
            "box_end_date": box.end_date,
            "box_days": box.days,
            "box_high": box.box_high,
            "box_low": box.box_low,
            "box_width": box.box_width,
            "box_position": box.box_position,
            "box_position_raw": box.box_position_raw,
            "box_low_test_count": box.low_test_count,
            "box_high_test_count": box.high_test_count,
            "box_first_half_volume": box.first_half_volume,
            "box_second_half_volume": box.second_half_volume,
            "box_volume_contraction_ratio": box.volume_contraction_ratio,
            "first_half_median_close": box.first_half_median_close,
            "second_half_median_close": box.second_half_median_close,
            "box_center_shift": box.center_shift,
            "box_break_reason": box.break_reason,
            "box_selection_reason": box.selection_reason,
            "compact_kline_enabled": compact.enabled,
            "compact_kline_pass": compact.passed,
            "compact_kline_score": compact.score,
            "box_quality_score": box.quality_score,
            "box_quality_tag": box.quality_tag,
            "avg_body_ratio_5": compact.avg_body_ratio,
            "max_body_ratio_5": compact.max_body_ratio,
            "compact_close_range_5": compact.close_range,
            "kline_overlap_pair_count": compact.overlap_pair_count,
            "avg_kline_overlap_ratio": compact.avg_overlap_ratio,
            "gap_count_5": compact.gap_count,
            "max_gap_ratio_5": compact.max_gap_ratio,
            "atr5": compact.atr5,
            "atr20": compact.atr20,
            "atr_contraction_ratio": compact.atr_contraction_ratio,
            "compact_kline_reasons": compact.reasons,
            "compact_kline_risk_tags": compact.risk_tags,
            **brooks.to_dict(),
            "highest_close_20": ind.highest_close_20,
            "highest_close_120": ind.highest_close_120,
            "pullback_from_20d_high": ind.pullback_from_20d_high,
            "range_5": ind.range_5,
            "range_10": ind.range_10,
            "close_range_5": ind.close_range_5,
            "consecutive_down_days": ind.consecutive_down_days,
            "consecutive_down_low": ind.consecutive_down_low,
            "consecutive_down_structure_version": ind.consecutive_down_structure_version,
            "consecutive_down_structure_pass": ind.consecutive_down_structure_pass,
            "consecutive_down_no_new_streak_low": ind.consecutive_down_no_new_streak_low,
            "consecutive_down_min_low_margin_pct": ind.consecutive_down_min_low_margin_pct,
            "consecutive_down_max_high_break_pct": ind.consecutive_down_max_high_break_pct,
            "start_date": start.start_date,
            "start_type": start.start_type,
            "start_grade": start.start_grade,
            "start_day_return": start.start_day_return,
            "start_day_volume_ratio": start.start_day_volume_ratio,
            "start_day_amount": start.start_day_amount,
            "start_day_close_position": start.start_day_close_position,
            "start_day_self_amount_percentile": start.start_day_self_amount_percentile,
            "start_low": start.start_low,
            "is_limit_up": start.is_limit_up,
            "is_one_word_limit_up": start.is_one_word_limit_up,
            "limit_up_pct": start.limit_up_pct,
            "days_since_start": start.days_since_start,
            "high_trigger": start.high_trigger,
            "start_event_quality_score": start.event_quality_score,
            "start_follow_through_return_5": start.follow_through_return_5,
            "start_gain_retention_ratio": start.gain_retention_ratio,
            "start_max_close_drawdown_5": start.max_close_drawdown_5,
            "start_failure_reasons": start.failure_reasons,
            "phase_status": self.phase.status,
            "consolidation_start_date": self.phase.consolidation_start_date,
            "tail_start_date": self.phase.tail_start_date,
            "signal_date": self.phase.signal_date,
            "start_age_days": self.phase.start_age_days,
            "consolidation_days": self.phase.consolidation_days,
            "tail_days": self.phase.tail_days,
            "tail_segmentation_status": self.phase.tail_segmentation_status,
            "tail_segmentation_score": self.phase.tail_segmentation_score,
            "tail_range_contraction_ratio": self.phase.tail_range_contraction_ratio,
            "tail_atr_contraction_ratio": self.phase.tail_atr_contraction_ratio,
            "tail_body_contraction_ratio": self.phase.tail_body_contraction_ratio,
            "pattern_type": self.pattern.pattern_type,
            "pattern_score": self.pattern.pattern_score,
            "pattern_start_date": self.pattern.pattern_start_date,
            "pattern_end_date": self.pattern.pattern_end_date,
            "pivot_source": self.pattern.pivot_source,
            "pivot_price": self.pattern.pivot_price,
            "pattern_low": self.pattern.pattern_low,
            "pattern_height": self.pattern.pattern_height,
            "pattern_depth_pct": self.pattern.depth_pct,
            "contraction_count": self.pattern.contraction_count,
            "key_support_price": support.key_support_price,
            "tactical_support_price": support.tactical_support_price,
            "prior_key_support_price": support.prior_key_support_price,
            "support_zone_low": support.support_zone_low,
            "support_zone_high": support.support_zone_high,
            "defense_support_price": support.defense_support_price,
            "main_support_ma": support.main_support_ma,
            "support_status": support.support_status,
            "support_test_count": support.support_test_count,
            "pivot_price": support.pivot_price,
            "box_height": support.box_height,
            "support_score": score.support_score,
            "support_cluster_sources": support.support_cluster_sources,
            "support_cluster_score": support.support_cluster_score,
            "support_reaction_score": support.support_reaction_score,
            "support_reaction_reasons": support.support_reaction_reasons,
            "support_reaction_risk_tags": support.support_reaction_risk_tags,
            "setup_quality_score": quality.score,
            "setup_gain_retention_ratio": quality.gain_retention_ratio,
            "distribution_day_count": quality.distribution_day_count,
            "up_down_volume_ratio": quality.up_down_volume_ratio,
            "volatility_contraction_ratio": quality.volatility_contraction_ratio,
            "failed_breakout_count": quality.failed_breakout_count,
            "relative_strength_trend": quality.relative_strength_trend,
            "setup_quality_reasons": quality.reasons,
            "setup_quality_risk_tags": quality.risk_tags,
            "suggested_buy_price": plan.suggested_buy_price,
            "buy_zone_low": plan.buy_zone_low,
            "buy_zone_high": plan.buy_zone_high,
            "stop_loss_price": plan.stop_loss_price,
            "target_price_1": plan.target_price_1,
            "target_price_2": plan.target_price_2,
            "target_price_3": plan.target_price_3,
            "objective_target_1": plan.objective_target_1,
            "objective_target_2": plan.objective_target_2,
            "execution_target_1_5r": plan.execution_target_1_5r,
            "execution_target_2r": plan.execution_target_2r,
            "execution_target_2_5r": plan.execution_target_2_5r,
            "execution_target_3_5r": plan.execution_target_3_5r,
            "risk_amount": plan.risk_amount,
            "reward_amount_1": plan.reward_amount_1,
            "reward_amount_2": plan.reward_amount_2,
            "reward_amount_3": plan.reward_amount_3,
            "risk_reward_ratio_1": plan.risk_reward_ratio_1,
            "risk_reward_ratio_2": plan.risk_reward_ratio_2,
            "risk_reward_ratio_3": plan.risk_reward_ratio_3,
            "objective_rr_1": plan.objective_rr_1,
            "objective_rr_2": plan.objective_rr_2,
            "signal_date": plan.signal_date or self.phase.signal_date,
            "valid_from_date": plan.valid_from_date,
            "valid_until_date": plan.valid_until_date,
            "buy_zone_valid_days": plan.buy_zone_valid_days,
            "suggested_limit_price": plan.suggested_limit_price,
            "execution_notes": plan.execution_notes,
            "entry_archetype": plan.entry_archetype,
            "strong_start_score": score.strong_start_score,
            "dry_stable_score": score.dry_stable_score,
            "risk_reward_score": score.risk_reward_score,
            "risk_control_score": score.risk_control_score,
            "total_score": score.total_score,
            "pattern_score_component": score.pattern_score_component,
            "tail_score": score.tail_score,
            "objective_rr_score": score.objective_rr_score,
            "relative_strength_risk_score": score.relative_strength_risk_score,
            "path_evidence_score": score.path_evidence_score,
            "score_model_version": score.score_model_version,
            "vcp_observation_eligible": vcp.eligible,
            "vcp_lifecycle_status": vcp.lifecycle_status,
            "vcp_origin_start_date": vcp.origin_start_date,
            "vcp_pattern_start_date": vcp.pattern_start_date,
            "vcp_pattern_end_date": vcp.pattern_end_date,
            "vcp_contraction_count": vcp.contraction_count,
            "vcp_contractions": vcp.contractions,
            "vcp_forming_round": vcp.forming_round,
            "vcp_pivot_price": vcp.pivot_price,
            "vcp_structure_low": vcp.structure_low,
            "vcp_distance_to_pivot_pct": vcp.distance_to_pivot_pct,
            "vcp_breakout_date": vcp.breakout_date,
            "vcp_days_since_breakout": vcp.days_since_breakout,
            "vcp_observation_reasons": vcp.reasons,
            "vcp_observation_risk_tags": vcp.risk_tags,
            "vcp_invalidation_reason": vcp.invalidation_reason,
            "vcp_history_qualified": vcp.history_qualified,
            "vcp_history_candidate_date": vcp.history_candidate_date,
            "vcp_history_candidate_type": vcp.history_candidate_type,
            "vcp_history_candidate_score": vcp.history_candidate_score,
            "vcp_history_source": vcp.history_source,
            "vcp_history_origin_start_date": vcp.history_origin_start_date,
            "vcp_quality_score": vcp_quality.score if vcp_quality.scored else None,
            "vcp_quality_grade": vcp_quality.grade,
            "vcp_quality_contraction_score": vcp_quality.contraction_score,
            "vcp_quality_range_score": vcp_quality.range_score,
            "vcp_quality_volume_score": vcp_quality.volume_score,
            "vcp_quality_low_score": vcp_quality.low_score,
            "vcp_quality_start_retention_score": vcp_quality.start_retention_score,
            "vcp_quality_time_score": vcp_quality.time_score,
            "vcp_quality_pivot_score": vcp_quality.pivot_score,
            "vcp_quality_breakout_score": vcp_quality.breakout_score,
            "vcp_quality_reasons": vcp_quality.reasons,
            "vcp_quality_warnings": vcp_quality.warnings,
            "vcp_quality_model_version": vcp_quality.model_version,
            "pre_market_candidate_type": self.pre_market_candidate_type,
            "candidate_type": self.candidate_type,
            "classification": self.classification,
            "lifecycle_status": self.lifecycle_status,
            "first_pool_date": ind.evaluation_date,
            "pool_age_trading_days": 0,
            "first_seen_date": ind.evaluation_date,
            "last_seen_date": ind.evaluation_date,
            "days_in_pool": 0,
            "exit_date": "",
            "exit_reason": "",
            "cooldown_until_date": "",
            "reentry_count": 0,
            "market_status": ind.market_status,
            "enable_market_filter": ind.market_filter_enabled,
            "market_filter_mode": ind.market_filter_mode,
            "risk_tags": ind.risk_tags,
            "warn_tags": ind.warn_tags,
            "reject_reasons": self.reject_reasons,
            "score_reasons": score.score_reasons,
            "suggestion": self.suggestion,
            "data_source": self.data_source,
            "kline_latest_date": ind.evaluation_date,
            "kline_fetched_at": self.kline_fetched_at,
            "quote_status": self.quote_status,
        }
