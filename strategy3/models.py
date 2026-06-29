"""策略3数据模型。"""
from dataclasses import dataclass, field


@dataclass
class Strategy3Indicators:
    """策略3指标结果，全部基于评估日及之前数据。"""
    ma5: float = 0.0
    ma10: float = 0.0
    ma20: float = 0.0
    ma60: float = 0.0
    ma120: float = 0.0
    return_3: float = 0.0
    return_20: float = 0.0
    return_60: float = 0.0
    return_120: float = 0.0
    high_120: float = 0.0
    drawdown_from_high_120: float = 0.0
    relative_strength_60: float = 0.0
    ma60_slope_20: float = 0.0
    recent_high: float = 0.0
    pullback_pct: float = 0.0
    range_5: float = 0.0
    range_10: float = 0.0
    range_20: float = 0.0
    range_compression_ok: bool = False
    close_range_5: float = 0.0
    volume_ratio_5_20: float = 0.0
    v3: float = 0.0
    v5: float = 0.0
    v10: float = 0.0
    v20: float = 0.0
    down_day_volume_ratio: float = 0.0
    volume_percentile_60: float = 0.0
    return_5: float = 0.0
    avg_abs_return_5: float = 0.0
    max_up_5: float = 0.0
    max_down_5: float = 0.0
    direction_efficiency_5: float = 0.0
    avg_close_position_5: float = 0.0
    min_close_5: float = 0.0
    min_close_10: float = 0.0
    previous_min_close_5: float = 0.0
    no_new_low: bool = False
    new_low_count_5: int = 0
    support_price_10: float = 0.0
    support_test_count: int = 0
    support_valid: bool = False
    short_support: float = 0.0
    short_support_zone_low: float = 0.0
    short_support_zone_high: float = 0.0
    key_support: float = 0.0
    key_support_zone_low: float = 0.0
    key_support_zone_high: float = 0.0
    strong_support: float = 0.0
    strong_support_zone_low: float = 0.0
    strong_support_zone_high: float = 0.0
    support_status: str = ""
    break_status: str = ""
    nearest_support_distance: float = 0.0
    support_sources: list[str] = field(default_factory=list)
    bear_body_shrink: bool = False
    bear_body_expanding: bool = False
    down_return_contracting: bool = False
    lower_shadow_count: int = 0
    down_volume_ratio_5: float = 0.0
    atr_ratio_5_20: float = 0.0
    has_big_down_volume: bool = False
    current_close: float = 0.0


@dataclass
class Strategy3Score:
    """策略3五模块评分。"""
    trend_score: int = 0
    pullback_score: int = 0
    volume_stability_score: int = 0
    second_breakout_score: int = 0
    risk_reward_score: int = 0
    total_score: int = 0
    level: str = ""
    score_reasons: list[str] = field(default_factory=list)


@dataclass
class Strategy3Risk:
    """策略3风险收益结果。"""
    support_price: float = 0.0
    stop_loss: float = 0.0
    target_1: float = 0.0
    risk_ratio: float = 0.0
    rr1: float = 0.0
    structural_support: float = 0.0
    structural_stop_loss: float = 0.0
    structural_risk_ratio: float = 0.0
    structural_rr1: float = 0.0
    tactical_support: float = 0.0
    tactical_stop_loss: float = 0.0
    tactical_risk_ratio: float = 0.0
    tactical_rr1: float = 0.0
    support_quality: str = ""
    short_support: float = 0.0
    short_support_zone_low: float = 0.0
    short_support_zone_high: float = 0.0
    key_support: float = 0.0
    key_support_zone_low: float = 0.0
    key_support_zone_high: float = 0.0
    strong_support: float = 0.0
    strong_support_zone_low: float = 0.0
    strong_support_zone_high: float = 0.0
    support_status: str = ""
    break_status: str = ""
    nearest_support_distance: float = 0.0
    support_sources: list[str] = field(default_factory=list)


@dataclass
class Strategy3TradeQuality:
    """策略3交易质量过滤层结果。"""
    trade_quality_score: int = 0
    volume_dry_score: int = 0
    price_stability_score: int = 0
    cannot_fall_score: int = 0
    balance_powerless_score: int = 0
    support_distance_pct: float = 0.0
    key_support_distance_pct: float = 0.0
    target_price: float = 0.0
    target_room_pct: float = 0.0
    estimated_rr: float = 0.0
    trade_state: str = ""
    trade_state_label: str = ""
    trigger_reasons: list[str] = field(default_factory=list)
    risk_warnings: list[str] = field(default_factory=list)
    invalid_conditions: list[str] = field(default_factory=list)
    reject_reasons: list[str] = field(default_factory=list)


@dataclass
class Strategy3Evaluation:
    """策略3最终评估结果。"""
    passed: bool
    code: str = ""
    name: str = ""
    evaluation_date: str = ""
    indicators: Strategy3Indicators = field(default_factory=Strategy3Indicators)
    risk: Strategy3Risk = field(default_factory=Strategy3Risk)
    trade_quality: Strategy3TradeQuality = field(default_factory=Strategy3TradeQuality)
    trend_score: int = 0
    pullback_score: int = 0
    volume_stability_score: int = 0
    second_breakout_score: int = 0
    risk_reward_score: int = 0
    total_score: int = 0
    level: str = ""
    current_close: float = 0.0
    score_reasons: list[str] = field(default_factory=list)
    reject_reasons: list[str] = field(default_factory=list)
    status_reason: str | None = None
