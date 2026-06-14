"""Strategy1 trusted backtest data models."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Strategy1HorizonPerformance:
    horizon_days: int = 0
    end_return: float | None = None
    max_upside: float | None = None
    max_drawdown: float | None = None
    result: str = "UNOBSERVED"
    days_to_target: int | None = None
    days_to_stop: int | None = None

    def to_dict(self) -> dict:
        return {
            "horizon_days": self.horizon_days,
            "end_return": round(self.end_return, 6) if self.end_return is not None else None,
            "max_upside": round(self.max_upside, 6) if self.max_upside is not None else None,
            "max_drawdown": round(self.max_drawdown, 6) if self.max_drawdown is not None else None,
            "result": self.result,
            "days_to_target": self.days_to_target,
            "days_to_stop": self.days_to_stop,
        }


@dataclass
class Strategy1BacktestSignal:
    code: str = ""
    name: str = ""
    evaluation_date: str = ""
    evaluation_index: int = 0
    pattern_kind: str = ""
    score: int = 0
    cup_depth_pct: float = 0.0
    cup_duration: int = 0
    handle_depth_pct: float = 0.0
    handle_duration: int = 0
    lip_deviation_pct: float = 0.0
    is_breakout: bool = False
    is_volume_breakout: bool = False
    breakout_price: float = 0.0
    current_close: float = 0.0
    volume_dry_score: int = 0
    price_stable_score: int = 0
    pattern_score_20: int = 0
    verdict_key: str = ""
    risk_percent: float = 0.0
    rr1: float = 0.0
    entry_zone_low: float = 0.0
    entry_zone_high: float = 0.0
    stop_loss: float = 0.0
    target_1: float = 0.0
    target_2: float = 0.0
    baseline_passed: bool = True
    experiment_passed: bool = True
    experiment_filter_reason: str = ""
    evaluation_snapshot: dict | None = None


@dataclass
class Strategy1BacktestOpportunity:
    code: str = ""
    name: str = ""
    first_detected_date: str = ""
    last_detected_date: str = ""
    pattern_kind: str = ""
    first_score: int = 0
    max_score: int = 0
    signal_count: int = 0
    signal_ids: list[int] = field(default_factory=list)
    entry_date: str = ""
    entry_price: float = 0.0
    stop_loss: float = 0.0
    exit_date: str = ""
    exit_price: float = 0.0
    exit_reason: str = ""
    realized_return: float | None = None
    mark_to_market_end_return: float | None = None
    holding_days: int = 0
    available_forward_days: int = 0
    horizons: dict[str, Strategy1HorizonPerformance] = field(default_factory=dict)
    market_context: dict | None = None
    evaluation_snapshot: dict | None = None


@dataclass
class Strategy1InsufficientStock:
    code: str = ""
    name: str = ""
    reason_code: str = ""
    available_days: int = 0
    required_days: int = 0
    earliest_date: str = ""
    latest_date: str = ""
