# strategy2/models.py
"""策略2数据模型 — 输入校验结果、指标、评分、风险、最终评估。"""
from dataclasses import dataclass, field


@dataclass
class IndicatorValidation:
    """输入数据校验结果。"""
    valid: bool
    data_days: int = 0
    window_days: int = 0
    reason: str = ""


@dataclass
class Strategy2Indicators:
    """策略2指标计算结果。

    所有指标仅使用评估日 T 及之前的数据计算。
    """
    v3: float = 0.0
    v5: float = 0.0
    v10: float = 0.0
    v20: float = 0.0
    volume_ratio_5_20: float = 0.0
    volume_percentile: float = 0.0
    volume_percentile_days: int = 0
    range_5: float = 0.0
    close_range_5: float = 0.0
    return_3: float = 0.0
    return_5: float = 0.0
    daily_return: float = 0.0


@dataclass
class Strategy2Score:
    """策略2评分结果。"""
    volume_dry_score: int = 0
    price_stable_score: int = 0
    total_score: int = 0
    level: str = ""
    score_reasons: list[str] = field(default_factory=list)


@dataclass
class Strategy2Risk:
    """策略2风险计算结果。"""
    key_support: float = 0.0
    buy_zone_low: float = 0.0
    buy_zone_high: float = 0.0
    stop_loss: float = 0.0
    risk_ratio: float = 0.0
    risk_level: str = ""


@dataclass
class Strategy2Evaluation:
    """策略2最终评估结果。

    由 ExtremeDryStableStrategyEngine.evaluate_at() 产生。
    """
    passed: bool
    code: str = ""
    name: str = ""
    evaluation_date: str = ""
    indicators: Strategy2Indicators = None
    volume_dry_score: int = 0
    price_stable_score: int = 0
    total_score: int = 0
    level: str = ""
    score_reasons: list[str] = field(default_factory=list)
    reject_reasons: list[str] = field(default_factory=list)
    risk: Strategy2Risk = None
    current_close: float = 0.0
    status_reason: str | None = None

    def __post_init__(self):
        if self.indicators is None:
            self.indicators = Strategy2Indicators()
        if self.risk is None:
            self.risk = Strategy2Risk()
