"""策略3回测数据模型。"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Strategy3HorizonPerformance:
    """单一观察周期内的机会表现。"""
    horizon_days: int = 0
    end_return: float = 0.0
    max_upside: float = 0.0
    max_drawdown: float = 0.0
    result: str = "UNOBSERVED"
    days_to_target: int | None = None
    days_to_stop: int | None = None

    def to_dict(self) -> dict:
        return {
            "horizon_days": self.horizon_days,
            "end_return": round(self.end_return, 6),
            "max_upside": round(self.max_upside, 6),
            "max_drawdown": round(self.max_drawdown, 6),
            "result": self.result,
            "days_to_target": self.days_to_target,
            "days_to_stop": self.days_to_stop,
        }


@dataclass
class Strategy3BacktestSignal:
    """策略3单个评估日的原始信号。"""
    code: str = ""
    name: str = ""
    evaluation_date: str = ""
    evaluation_index: int = 0
    total_score: int = 0
    level: str = ""
    current_close: float = 0.0
    trend_score: int = 0
    pullback_score: int = 0
    volume_stability_score: int = 0
    second_breakout_score: int = 0
    risk_reward_score: int = 0
    trade_state: str = ""
    trade_state_label: str = ""
    trade_quality_score: int = 0
    volume_dry_score: int = 0
    price_stability_score: int = 0
    cannot_fall_score: int = 0
    balance_powerless_score: int = 0
    support_price: float = 0.0
    stop_loss: float = 0.0
    target_price: float = 0.0
    risk_ratio: float = 0.0
    rr1: float = 0.0
    pullback_pct: float = 0.0
    volume_ratio_5_20: float = 0.0
    evaluation_snapshot: dict = field(default_factory=dict)


@dataclass
class Strategy3BacktestOpportunity:
    """策略3一次去重后的交易机会。"""
    code: str = ""
    name: str = ""
    first_detected_date: str = ""
    last_detected_date: str = ""
    consecutive_hit_days: int = 0
    first_score: int = 0
    max_score: int = 0
    level: str = ""
    trade_state: str = ""
    trade_state_label: str = ""
    trade_quality_score: int = 0
    entry_close: float = 0.0
    support_price: float = 0.0
    stop_loss: float = 0.0
    target_price: float = 0.0
    risk_ratio: float = 0.0
    rr1: float = 0.0
    trend_score: int = 0
    pullback_score: int = 0
    volume_stability_score: int = 0
    second_breakout_score: int = 0
    risk_reward_score: int = 0
    volume_dry_score: int = 0
    price_stability_score: int = 0
    cannot_fall_score: int = 0
    balance_powerless_score: int = 0
    pullback_pct: float = 0.0
    volume_ratio_5_20: float = 0.0
    evaluation_snapshot: dict = field(default_factory=dict)
    signal_ids: list[int] = field(default_factory=list)
    signal_count: int = 0
    execution_model: str = ""
    entry_date: str = ""
    entry_price: float = 0.0
    exit_date: str = ""
    exit_price: float = 0.0
    exit_reason: str = ""
    realized_return: float = 0.0
    mark_to_market_end_return: float = 0.0
    holding_days: int = 0
    available_forward_days: int = 0
    horizons: dict[str, Strategy3HorizonPerformance] = field(default_factory=dict)


@dataclass
class Strategy3BacktestSummary:
    """策略3回测汇总。"""
    total_stocks: int = 0
    stocks_with_opportunities: int = 0
    total_signals: int = 0
    total_opportunities: int = 0
    entered_opportunities: int = 0
    no_entry_count: int = 0
    stop_count: int = 0
    target_count: int = 0
    unresolved_count: int = 0
    total_eval_days: int = 0
    group_stats: dict = field(default_factory=dict)
