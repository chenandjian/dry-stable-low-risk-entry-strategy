"""Strategy5 data models."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Strategy5Indicators:
    evaluation_date: str = ""
    close: float = 0.0
    daily_return: float = 0.0
    change_pct: float = 0.0
    trading_days: int = 0
    avg_turnover_60d: float = 0.0
    avg_turnover_30d: float = 0.0
    avg_turnover_10d: float = 0.0
    ma5: float = 0.0
    ma10: float = 0.0
    ma20: float = 0.0
    ma50: float = 0.0
    ma100: float = 0.0
    ma120: float = 0.0
    ma250: float = 0.0
    distance_to_ma5: float = 0.0
    distance_to_ma10: float = 0.0
    distance_to_ma20: float = 0.0
    recent_5d_return: float = 0.0
    recent_10d_return: float = 0.0
    recent_20d_return: float = 0.0
    recent_50d_return: float = 0.0
    drawdown_from_20d_high: float = 0.0
    amplitude_5d: float = 0.0
    amplitude_10d: float = 0.0
    max_decline_5d: float = 0.0
    v3: float = 0.0
    v5: float = 0.0
    v10: float = 0.0
    v20: float = 0.0
    v50: float = 0.0
    volume_ratio_5_20: float = 0.0
    volume_ratio_5_50: float = 0.0
    volume_percentile_60: float = 0.0
    down_volume_ratio_5: float = 0.0
    down_day_avg_volume_ratio_20: float = 0.0
    has_big_down_volume: bool = False
    consecutive_heavy_bear_days: int = 0
    close_range_5: float = 0.0
    atr_ratio_5_20: float = 0.0
    direction_efficiency_5: float = 0.0
    no_new_low_5: bool = True
    bear_body_shrink: bool = False
    down_return_contracting: bool = False
    dry_support_price: float = 0.0
    dry_support_distance: float = 0.0
    dry_support_valid: bool = False
    near_120d_high_ratio: float = 0.0
    close_20d_high: float = 0.0
    close_120d_high: float = 0.0
    strength_trigger: str = ""
    high_trigger: str = ""
    range_5_tag: str = ""
    range_10_tag: str = ""
    pullback_tag: str = ""
    risk_tags: list[str] = field(default_factory=list)
    warn_tags: list[str] = field(default_factory=list)
    ma20_slope_5d: float = 0.0
    ma50_slope_10d: float = 0.0
    has_volume_up_decline: bool = False


@dataclass
class Strategy5VolumeDry:
    volume_dry_score: int = 0
    volume_dry_level: str = "NOT_DRY"
    volume_dry_reasons: list[str] = field(default_factory=list)
    volume_dry_warnings: list[str] = field(default_factory=list)
    volume_dry_rejects: list[str] = field(default_factory=list)


@dataclass
class Strategy5Support:
    support_status: str
    main_support_ma: str = ""
    main_support_price: float = 0.0
    main_support_distance: float = 0.0
    support_score: int = 0


@dataclass
class Strategy5Score:
    technical_score: float = 0.0
    capital_score: float = 0.0
    trend_score: float = 0.0
    support_quality_score: float = 0.0
    total_score: float = 0.0
    score_reasons: list[str] = field(default_factory=list)


@dataclass
class Strategy5Evaluation:
    code: str
    name: str
    indicators: Strategy5Indicators
    support: Strategy5Support
    score: Strategy5Score
    volume_dry: Strategy5VolumeDry = field(default_factory=Strategy5VolumeDry)
    candidate_type: str = "REJECTED"
    classification: str = "rejected"
    reject_reasons: list[str] = field(default_factory=list)
    status_reason: str = ""
    data_source: str = ""
    kline_latest_date: str = ""
    kline_fetched_at: str = ""
    quote_status: str = ""

    @property
    def passed(self) -> bool:
        return self.candidate_type in {"BUY_CANDIDATE", "KEY_CANDIDATE", "WATCH_CANDIDATE"}

    @property
    def is_trade_candidate(self) -> bool:
        return self.candidate_type == "BUY_CANDIDATE"

    def to_candidate_dict(self) -> dict:
        ind = self.indicators
        sup = self.support
        score = self.score
        return {
            "code": self.code,
            "name": self.name,
            "evaluation_date": ind.evaluation_date,
            "close": ind.close,
            "daily_return": ind.daily_return,
            "change_pct": ind.change_pct,
            "trading_days": ind.trading_days,
            "avg_turnover_60d": ind.avg_turnover_60d,
            "avg_turnover_30d": ind.avg_turnover_30d,
            "avg_turnover_10d": ind.avg_turnover_10d,
            "ma5": ind.ma5,
            "ma10": ind.ma10,
            "ma20": ind.ma20,
            "ma50": ind.ma50,
            "ma100": ind.ma100,
            "ma120": ind.ma120,
            "ma250": ind.ma250,
            "distance_to_ma5": ind.distance_to_ma5,
            "distance_to_ma10": ind.distance_to_ma10,
            "distance_to_ma20": ind.distance_to_ma20,
            "recent_5d_return": ind.recent_5d_return,
            "recent_10d_return": ind.recent_10d_return,
            "recent_20d_return": ind.recent_20d_return,
            "recent_50d_return": ind.recent_50d_return,
            "drawdown_from_20d_high": ind.drawdown_from_20d_high,
            "amplitude_5d": ind.amplitude_5d,
            "amplitude_10d": ind.amplitude_10d,
            "support_status": sup.support_status,
            "main_support_ma": sup.main_support_ma,
            "main_support_price": sup.main_support_price,
            "main_support_distance": sup.main_support_distance,
            "support_score": sup.support_score,
            "candidate_type": self.candidate_type,
            "classification": self.classification,
            "is_trade_candidate": self.is_trade_candidate,
            "range_5_tag": ind.range_5_tag,
            "range_10_tag": ind.range_10_tag,
            "pullback_tag": ind.pullback_tag,
            "risk_tags": ind.risk_tags,
            "warn_tags": ind.warn_tags,
            "near_120d_high_ratio": ind.near_120d_high_ratio,
            "close_20d_high": ind.close_20d_high,
            "close_120d_high": ind.close_120d_high,
            "strength_trigger": ind.strength_trigger,
            "high_trigger": ind.high_trigger,
            "ma20_slope_5d": ind.ma20_slope_5d,
            "ma50_slope_10d": ind.ma50_slope_10d,
            "max_decline_5d": ind.max_decline_5d,
            "v3": ind.v3,
            "v5": ind.v5,
            "v10": ind.v10,
            "v20": ind.v20,
            "v50": ind.v50,
            "volume_ratio_5_20": ind.volume_ratio_5_20,
            "volume_ratio_5_50": ind.volume_ratio_5_50,
            "volume_percentile_60": ind.volume_percentile_60,
            "down_volume_ratio_5": ind.down_volume_ratio_5,
            "down_day_avg_volume_ratio_20": ind.down_day_avg_volume_ratio_20,
            "close_range_5": ind.close_range_5,
            "atr_ratio_5_20": ind.atr_ratio_5_20,
            "direction_efficiency_5": ind.direction_efficiency_5,
            "dry_support_price": ind.dry_support_price,
            "dry_support_distance": ind.dry_support_distance,
            "dry_support_valid": ind.dry_support_valid,
            "volume_dry_score": self.volume_dry.volume_dry_score,
            "volume_dry_level": self.volume_dry.volume_dry_level,
            "volume_dry_reasons": self.volume_dry.volume_dry_reasons,
            "volume_dry_warnings": self.volume_dry.volume_dry_warnings,
            "volume_dry_rejects": self.volume_dry.volume_dry_rejects,
            "technical_score": score.technical_score,
            "capital_score": score.capital_score,
            "trend_score": score.trend_score,
            "support_quality_score": score.support_quality_score,
            "total_score": score.total_score,
            "reject_reasons": self.reject_reasons,
            "score_reasons": score.score_reasons,
            "data_source": self.data_source,
            "kline_latest_date": self.kline_latest_date,
            "kline_fetched_at": self.kline_fetched_at,
            "quote_status": self.quote_status,
        }
