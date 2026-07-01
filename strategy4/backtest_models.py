"""Strategy4 backtest data models."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Strategy4UnobservedDay:
    evaluation_date: str
    reason_code: str
    detail: str = ""


@dataclass
class Strategy4BacktestSignal:
    code: str = ""
    name: str = ""
    topic_id: str = ""
    topic_name: str = ""
    evaluation_date: str = ""
    evaluation_index: int = 0
    hot_topic_score: float = 0.0
    leader_strength_score: float = 0.0
    tradability_score: float = 0.0
    first_wave_return: float = 0.0
    pullback_pct: float = 0.0
    pullback_days: int = 0
    support_price: float = 0.0
    stop_loss: float = 0.0
    target_price: float = 0.0
    risk_ratio: float = 0.0
    reward_risk_ratio: float = 0.0
    evaluation_snapshot: dict = field(default_factory=dict)


@dataclass
class Strategy4BacktestOpportunity:
    code: str = ""
    name: str = ""
    topic_id: str = ""
    topic_name: str = ""
    first_detected_date: str = ""
    hot_topic_score: float = 0.0
    leader_strength_score: float = 0.0
    tradability_score: float = 0.0
    first_wave_return: float = 0.0
    pullback_pct: float = 0.0
    pullback_days: int = 0
    signal_close: float = 0.0
    support_price: float = 0.0
    stop_loss: float = 0.0
    target_price: float = 0.0
    risk_ratio: float = 0.0
    reward_risk_ratio: float = 0.0
    execution_model: str = ""
    entry_date: str = ""
    entry_price: float = 0.0
    exit_date: str = ""
    exit_price: float = 0.0
    exit_reason: str = ""
    realized_return: float = 0.0
    holding_days: int = 0
    available_forward_days: int = 0
    evaluation_snapshot: dict = field(default_factory=dict)


@dataclass
class Strategy4BacktestSummary:
    evaluation_days: int = 0
    observed_snapshot_days: int = 0
    unobserved_snapshot_days: int = 0
    total_signals: int = 0
    total_opportunities: int = 0
    entered_opportunities: int = 0
    no_entry_count: int = 0
    stop_count: int = 0
    target_count: int = 0
    unresolved_count: int = 0
    unobserved_forward_count: int = 0
    avg_realized_return: float = 0.0
    profit_factor: float | None = None


@dataclass
class Strategy4BacktestResult:
    task_id: str = ""
    config_snapshot: dict = field(default_factory=dict)
    summary: Strategy4BacktestSummary = field(default_factory=Strategy4BacktestSummary)
    signals: list[Strategy4BacktestSignal] = field(default_factory=list)
    opportunities: list[Strategy4BacktestOpportunity] = field(default_factory=list)
    unobserved: list[Strategy4UnobservedDay] = field(default_factory=list)
