"""Result models for the Strategy6 Brooks tail path."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class BrooksContextResult:
    context_type: str = "INVALID_CONTEXT"
    passed: bool = False
    watch_only: bool = False
    ma20_slope: float = 0.0
    lower_high_count: int = 0
    lower_low_count: int = 0
    lower_high_low_sequence_count: int = 0
    reasons: list[str] = field(default_factory=list)
    risk_tags: list[str] = field(default_factory=list)


@dataclass
class BrooksSellingPressureResult:
    exhausted: bool = False
    strong_bear_bar_count: int = 0
    strong_bear_bar_dates: list[str] = field(default_factory=list)
    bear_follow_through_count: int = 0
    bear_follow_through_dates: list[str] = field(default_factory=list)
    max_consecutive_bear_bars: int = 0
    bear_body_contraction_ratio: float | None = None
    bear_follow_through_failed: bool = False
    bear_follow_through_failed_date: str = ""
    reasons: list[str] = field(default_factory=list)
    risk_tags: list[str] = field(default_factory=list)


@dataclass
class BrooksCompactStructureResult:
    structure_type: str = "NO_COMPACT"
    direction_change_count: int = 0
    long_shadow_bar_count: int = 0
    barb_wire_risk: bool = False
    reasons: list[str] = field(default_factory=list)
    risk_tags: list[str] = field(default_factory=list)


@dataclass
class BrooksStructureResult:
    micro_double_bottom: bool = False
    failed_bear_breakout: bool = False
    failed_bear_breakout_date: str = ""
    reclaim_date: str = ""
    bear_follow_through_failed: bool = False
    bear_follow_through_failed_date: str = ""
    orderly_compression_at_support: bool = False
    second_entry_long_ready: bool = False
    first_recent_low_date: str = ""
    first_recent_low_price: float | None = None
    second_recent_low_date: str = ""
    second_recent_low_price: float | None = None
    second_low_similarity: float | None = None
    second_entry_signal_date: str = ""
    second_entry_signal_high: float | None = None
    second_entry_trigger_price: float | None = None
    setup_types: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    risk_tags: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return bool(self.setup_types)


@dataclass
class BrooksTradeTriggerResult:
    ready: bool = False
    trigger_type: str = ""
    trigger_price: float | None = None
    trigger_valid_until: str = ""
    second_entry_triggered: bool = False
    failed_bear_breakout_confirmed: bool = False
    breakout_bar_pass: bool = False
    breakout_follow_through_pass: bool = False
    breakout_pullback_pass: bool = False
    reasons: list[str] = field(default_factory=list)
    risk_tags: list[str] = field(default_factory=list)


@dataclass
class BrooksTailResult:
    enabled: bool = False
    passed: bool = False
    score: int = 0
    premium: bool = False
    status: str = "BROOKS_DISABLED"
    bull_context_pass: bool = False
    selling_pressure_exhausted: bool = False
    price_stable_pass: bool = False
    volume_dry_pass: bool = False
    support_not_broken: bool = False
    setup_pass: bool = False
    hard_reject: bool = False
    context: BrooksContextResult = field(default_factory=BrooksContextResult)
    selling_pressure: BrooksSellingPressureResult = field(default_factory=BrooksSellingPressureResult)
    compact_structure: BrooksCompactStructureResult = field(default_factory=BrooksCompactStructureResult)
    structure: BrooksStructureResult = field(default_factory=BrooksStructureResult)
    trade_trigger: BrooksTradeTriggerResult = field(default_factory=BrooksTradeTriggerResult)
    metrics: dict[str, Any] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)
    reject_reasons: list[str] = field(default_factory=list)
    risk_tags: list[str] = field(default_factory=list)

    @classmethod
    def disabled(cls) -> "BrooksTailResult":
        return cls()

    def to_dict(self) -> dict[str, Any]:
        detail = asdict(self)
        return {
            "brooks_tail_enabled": self.enabled,
            "brooks_tail_pass": self.passed,
            "brooks_tail_score": self.score,
            "brooks_tail_premium": self.premium,
            "brooks_status": self.status,
            "brooks_trade_ready": self.trade_trigger.ready,
            "brooks_trade_trigger_type": self.trade_trigger.trigger_type,
            "brooks_trigger_price": self.trade_trigger.trigger_price,
            "brooks_trigger_valid_until": self.trade_trigger.trigger_valid_until,
            "brooks_result": detail,
        }
