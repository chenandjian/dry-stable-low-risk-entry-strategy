"""Strategy4 data models."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class HotTopicScore:
    topic_id: str
    topic_name: str
    topic_type: str
    source: str
    status: str
    hot_topic_score: float
    price_strength_score: float = 0.0
    amount_strength_score: float = 0.0
    fund_flow_score: float = 0.0
    breadth_score: float = 0.0
    leader_limit_score: float = 0.0
    breakout_score: float = 0.0
    signal_count: int = 0
    strong_signals: list[str] = field(default_factory=list)
    noise_reason: str = ""
    leading_stock_code: str = ""
    leading_stock_name: str = ""
    raw_snapshot: dict = field(default_factory=dict)


@dataclass
class LeaderScore:
    code: str
    name: str
    topic_id: str
    topic_name: str
    leader_type: str
    leader_strength_score: float
    tradability_score: float
    status: str
    reasons: list[str] = field(default_factory=list)


@dataclass
class FirstWaveResult:
    passed: bool
    first_wave_return: float = 0.0
    strong_day_count: int = 0
    reasons: list[str] = field(default_factory=list)
    reject_reasons: list[str] = field(default_factory=list)


@dataclass
class PullbackResult:
    passed: bool
    pullback_pct: float = 0.0
    pullback_days: int = 0
    reasons: list[str] = field(default_factory=list)
    reject_reasons: list[str] = field(default_factory=list)


@dataclass
class SecondWaveResult:
    passed: bool
    signals: list[str] = field(default_factory=list)
    reject_reasons: list[str] = field(default_factory=list)


@dataclass
class RiskRewardResult:
    passed: bool
    support_price: float = 0.0
    stop_loss: float = 0.0
    target_price: float = 0.0
    risk_ratio: float = 0.0
    reward_risk_ratio: float = 0.0
    reject_reasons: list[str] = field(default_factory=list)

