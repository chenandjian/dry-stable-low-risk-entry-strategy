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
    close_range_5: float = 0.0
    volume_ratio_5_20: float = 0.0
    v5: float = 0.0
    v10: float = 0.0
    v20: float = 0.0
    down_day_volume_ratio: float = 0.0
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


@dataclass
class Strategy3Evaluation:
    """策略3最终评估结果。"""
    passed: bool
    code: str = ""
    name: str = ""
    evaluation_date: str = ""
    indicators: Strategy3Indicators = field(default_factory=Strategy3Indicators)
    risk: Strategy3Risk = field(default_factory=Strategy3Risk)
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

