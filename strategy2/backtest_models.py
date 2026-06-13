# strategy2/backtest_models.py
"""策略2回测数据模型。"""
from dataclasses import dataclass, field


@dataclass
class HorizonPerformance:
    """单一短线观察周期的表现。"""
    horizon_days: int = 0
    end_return: float = 0.0
    max_upside: float = 0.0
    max_drawdown: float = 0.0
    result: str = "UNOBSERVED"  # SUCCESS / FAILED / UNRESOLVED / UNOBSERVED
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
class BacktestSignal:
    """单个判断日的原始命中信号。"""
    code: str = ""
    name: str = ""
    evaluation_date: str = ""
    evaluation_index: int = 0  # 在完整评估日序列中的位置
    score: int = 0
    level: str = ""
    current_close: float = 0.0
    stop_loss: float = 0.0
    risk_ratio: float = 0.0
    volume_dry_score: int = 0
    price_stable_score: int = 0
    trend_type: str = ""
    trend_evidence_score: int = 0
    evaluation_snapshot: dict | None = None
    baseline_passed: bool = True
    experiment_passed: bool = True
    experiment_filter_reason: str = ""
    opportunity_type: str = ""


@dataclass
class BacktestOpportunity:
    """一次去重后的回测机会。"""
    code: str = ""
    name: str = ""
    first_detected_date: str = ""
    last_detected_date: str = ""
    consecutive_hit_days: int = 0
    first_score: int = 0
    max_score: int = 0
    level: str = ""
    entry_close: float = 0.0
    stop_loss: float = 0.0
    risk_ratio: float = 0.0
    volume_dry_score: int = 0
    price_stable_score: int = 0
    trend_type: str = ""
    trend_evidence_score: int = 0
    evaluation_snapshot: dict | None = None
    horizons: dict[str, HorizonPerformance] = field(default_factory=dict)
    # Signal traceability
    signal_ids: list[int] = field(default_factory=list)
    signal_count: int = 0
    # Execution model fields
    execution_model: str = ""
    entry_date: str = ""
    entry_price: float = 0.0
    exit_date: str = ""
    exit_price: float = 0.0
    exit_reason: str = ""  # TARGET / STOP / TIME_EXIT / UNOBSERVED_ENTRY / NO_ENTRY_GAP / NO_ENTRY_ABOVE_BUY_ZONE
    realized_return: float = 0.0
    mark_to_market_end_return: float = 0.0
    holding_days: int = 0
    available_forward_days: int = 0
    opportunity_type: str = ""
    entry_confirmation_type: str = ""
    entry_confirmation_date: str = ""
    entry_confirmation_price: float = 0.0
    entry_confirmation_status: str = ""
    time_exit_days: int | None = None
    market_context: dict | None = None


@dataclass
class InsufficientStock:
    """数据不足无法回测的股票。"""
    code: str = ""
    name: str = ""
    reason_code: str = ""  # NO_LOCAL_DATA / INSUFFICIENT_HISTORY_DATA / LIMITED_EVALUATION_RANGE / INVALID_LOCAL_DATA
    available_days: int = 0
    required_days: int = 0
    earliest_date: str = ""
    latest_date: str = ""


@dataclass
class BacktestSummary:
    """回测汇总报告。"""
    total_stocks: int = 0
    stocks_with_opportunities: int = 0
    total_opportunities: int = 0
    avg_opportunities_per_eval_day: float = 0.0
    complete_observed_count: int = 0
    unobserved_count: int = 0
    insufficient_stocks_count: int = 0
    failed_stocks_count: int = 0
    horizon_stats: dict = field(default_factory=dict)  # key="3"/"5"/"10"/"20"
    total_eval_days: int = 0
    liquidity_filtered_days: int = 0
    trend_skipped_days: int = 0
