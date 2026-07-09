"""Strategy6 data models."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Strategy6Indicators:
    evaluation_date: str = ""
    current_price: float = 0.0
    daily_return: float = 0.0
    trading_days: int = 0
    ma5: float = 0.0
    ma10: float = 0.0
    ma20: float = 0.0
    ma50: float = 0.0
    ma120: float = 0.0
    ma250: float = 0.0
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
    highest_close_20: float = 0.0
    highest_close_120: float = 0.0
    highest_close_250: float = 0.0
    pullback_from_20d_high: float = 0.0
    range_5: float = 0.0
    range_10: float = 0.0
    close_range_5: float = 0.0
    relative_strength_20: float = 0.0
    relative_strength_10_sector: float = 0.0
    sector_member_new_high_count: int = 0
    market_status: str = "UNKNOWN"
    sector_strength_status: str = "UNKNOWN"
    market_filter_enabled: bool = False
    sector_filter_enabled: bool = False
    market_filter_mode: str = "downgrade"
    sector_filter_mode: str = "downgrade"
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
    is_limit_up: bool = False
    is_one_word_limit_up: bool = False
    limit_up_pct: float = 0.0
    high_trigger: str = ""


@dataclass
class Strategy6Support:
    support_status: str = "SUPPORT_FAILED"
    main_support_ma: str = ""
    key_support_price: float = 0.0
    support_zone_low: float = 0.0
    support_zone_high: float = 0.0
    defense_support_price: float = 0.0
    support_test_count: int = 0
    pivot_price: float = 0.0
    box_height: float = 0.0
    support_score: int = 0


@dataclass
class Strategy6DryTail:
    dry_stable_score: int = 0
    dry_tail_pass: bool = False
    reasons: list[str] = field(default_factory=list)
    rejects: list[str] = field(default_factory=list)


@dataclass
class Strategy6TradePlan:
    suggested_buy_price: float | None = None
    buy_zone_low: float = 0.0
    buy_zone_high: float = 0.0
    stop_loss_price: float = 0.0
    target_price_1: float = 0.0
    target_price_2: float = 0.0
    target_price_3: float = 0.0
    risk_amount: float = 0.0
    reward_amount_1: float = 0.0
    reward_amount_2: float = 0.0
    reward_amount_3: float = 0.0
    risk_reward_ratio_1: float = 0.0
    risk_reward_ratio_2: float = 0.0
    risk_reward_ratio_3: float = 0.0


@dataclass
class Strategy6Score:
    strong_start_score: int = 0
    support_score: int = 0
    dry_stable_score: int = 0
    risk_reward_score: int = 0
    risk_control_score: int = 0
    total_score: int = 0
    score_reasons: list[str] = field(default_factory=list)


@dataclass
class Strategy6Evaluation:
    code: str
    name: str
    sector_name: str
    indicators: Strategy6Indicators
    start: Strategy6Start
    support: Strategy6Support
    dry_tail: Strategy6DryTail
    trade_plan: Strategy6TradePlan
    score: Strategy6Score
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
        return {
            "code": self.code,
            "name": self.name,
            "sector_name": self.sector_name,
            "evaluation_date": ind.evaluation_date,
            "current_price": ind.current_price,
            "close": ind.current_price,
            "daily_return": ind.daily_return,
            "trading_days": ind.trading_days,
            "ma5": ind.ma5,
            "ma10": ind.ma10,
            "ma20": ind.ma20,
            "ma50": ind.ma50,
            "ma120": ind.ma120,
            "ma250": ind.ma250,
            "return_5": ind.return_5,
            "return_10": ind.return_10,
            "return_20": ind.return_20,
            "relative_strength_20": ind.relative_strength_20,
            "relative_strength_10_sector": ind.relative_strength_10_sector,
            "sector_member_new_high_count": ind.sector_member_new_high_count,
            "amount_avg_10": ind.amount_avg_10,
            "amount_avg_30": ind.amount_avg_30,
            "amount_avg_60": ind.amount_avg_60,
            "v3": ind.v3,
            "v5": ind.v5,
            "v10": ind.v10,
            "v20": ind.v20,
            "volume_ratio_5_20": ind.volume_ratio_5_20,
            "highest_close_20": ind.highest_close_20,
            "highest_close_120": ind.highest_close_120,
            "pullback_from_20d_high": ind.pullback_from_20d_high,
            "range_5": ind.range_5,
            "range_10": ind.range_10,
            "close_range_5": ind.close_range_5,
            "start_date": start.start_date,
            "start_type": start.start_type,
            "start_grade": start.start_grade,
            "start_day_return": start.start_day_return,
            "start_day_volume_ratio": start.start_day_volume_ratio,
            "start_day_amount": start.start_day_amount,
            "start_day_close_position": start.start_day_close_position,
            "is_limit_up": start.is_limit_up,
            "is_one_word_limit_up": start.is_one_word_limit_up,
            "limit_up_pct": start.limit_up_pct,
            "high_trigger": start.high_trigger,
            "key_support_price": support.key_support_price,
            "support_zone_low": support.support_zone_low,
            "support_zone_high": support.support_zone_high,
            "defense_support_price": support.defense_support_price,
            "main_support_ma": support.main_support_ma,
            "support_status": support.support_status,
            "support_test_count": support.support_test_count,
            "pivot_price": support.pivot_price,
            "box_height": support.box_height,
            "support_score": score.support_score,
            "suggested_buy_price": plan.suggested_buy_price,
            "buy_zone_low": plan.buy_zone_low,
            "buy_zone_high": plan.buy_zone_high,
            "stop_loss_price": plan.stop_loss_price,
            "target_price_1": plan.target_price_1,
            "target_price_2": plan.target_price_2,
            "target_price_3": plan.target_price_3,
            "risk_amount": plan.risk_amount,
            "reward_amount_1": plan.reward_amount_1,
            "reward_amount_2": plan.reward_amount_2,
            "reward_amount_3": plan.reward_amount_3,
            "risk_reward_ratio_1": plan.risk_reward_ratio_1,
            "risk_reward_ratio_2": plan.risk_reward_ratio_2,
            "risk_reward_ratio_3": plan.risk_reward_ratio_3,
            "strong_start_score": score.strong_start_score,
            "dry_stable_score": score.dry_stable_score,
            "risk_reward_score": score.risk_reward_score,
            "risk_control_score": score.risk_control_score,
            "total_score": score.total_score,
            "candidate_type": self.candidate_type,
            "classification": self.classification,
            "lifecycle_status": self.lifecycle_status,
            "first_pool_date": ind.evaluation_date,
            "pool_age_trading_days": 0,
            "market_status": ind.market_status,
            "sector_strength_status": ind.sector_strength_status,
            "enable_market_filter": ind.market_filter_enabled,
            "enable_sector_filter": ind.sector_filter_enabled,
            "market_filter_mode": ind.market_filter_mode,
            "sector_filter_mode": ind.sector_filter_mode,
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
