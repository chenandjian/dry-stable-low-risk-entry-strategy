# strategy2/engine.py
"""策略2唯一评估入口 — ExtremeDryStableStrategyEngine。

组合指标、评分、否决、风险模块，输出最终评估结果。
不依赖策略1的任何形态检测、评分、分析或决策模块。
"""
import logging
from strategy2.models import (
    IndicatorValidation,
    Strategy2Indicators,
    Strategy2Score,
    Strategy2Risk,
    Strategy2Evaluation,
)
from strategy2.indicators import validate_strategy_data, compute_indicators
from strategy2.scorer import compute_total_score
from strategy2.rejection import check_rejection_rules
from strategy2.risk import compute_key_support, compute_risk

logger = logging.getLogger(__name__)


class ExtremeDryStableStrategyEngine:
    """策略2「极致量干价稳」唯一评估入口。

    使用方法:
        engine = ExtremeDryStableStrategyEngine(strategy2_config)
        evaluation = engine.evaluate_at(data, code="000001", name="平安银行")
    """

    def __init__(self, config: dict):
        """初始化并校验策略2配置。

        Raises:
            ValueError: 配置参数非法。
        """
        self.strategy_window_days = int(config.get("strategy_window_days", 120))
        self.min_required = int(config.get("minimum_required_days", 60))
        self.candidate_min_score = int(config.get("candidate_min_score", 70))
        self.max_risk_ratio = float(config.get("max_risk_ratio", 0.05))
        self.support_lookback_days = int(config.get("support_lookback_days", 10))
        self.buy_zone_max_premium = float(config.get("buy_zone_max_premium", 0.03))
        self.stop_loss_buffer = float(config.get("stop_loss_buffer", 0.03))

        self._validate_config()

    def _validate_config(self):
        """校验配置参数合法性。"""
        if self.strategy_window_days < self.min_required:
            raise ValueError(
                f"strategy_window_days ({self.strategy_window_days}) must be >= "
                f"minimum_required_days ({self.min_required})"
            )
        if self.min_required < 60:
            raise ValueError(
                f"minimum_required_days ({self.min_required}) must be >= 60"
            )
        if self.support_lookback_days < 2:
            raise ValueError(
                f"support_lookback_days ({self.support_lookback_days}) must be >= 2"
            )
        if not 0 <= self.candidate_min_score <= 100:
            raise ValueError(
                f"candidate_min_score ({self.candidate_min_score}) must be in [0, 100]"
            )
        if not 0 < self.max_risk_ratio < 1:
            raise ValueError(
                f"max_risk_ratio ({self.max_risk_ratio}) must be in (0, 1)"
            )
        if not 0 < self.buy_zone_max_premium <= 0.20:
            raise ValueError(
                f"buy_zone_max_premium ({self.buy_zone_max_premium}) must be in (0, 0.20]"
            )
        if not 0 < self.stop_loss_buffer <= 0.20:
            raise ValueError(
                f"stop_loss_buffer ({self.stop_loss_buffer}) must be in (0, 0.20]"
            )

    def evaluate_at(
        self,
        data: list[dict],
        *,
        code: str = "",
        name: str = "",
    ) -> Strategy2Evaluation:
        """对单只股票在评估日执行完整策略2评估。

        Args:
            data: 日线数据（按日期升序）。调用方负责保证数据不含评估日之后的信息。
            code: 股票代码。
            name: 股票名称。

        Returns:
            Strategy2Evaluation — passed=True 表示满足所有入选条件。
        """
        # 1. 数据校验
        validation = validate_strategy_data(data, self.strategy_window_days, self.min_required)
        if not validation.valid:
            return Strategy2Evaluation(
                passed=False,
                code=code,
                name=name,
                evaluation_date=data[-1]["date"] if data else "",
                status_reason=validation.reason,
            )

        evaluation_date = data[-1]["date"]
        current_close = data[-1]["close"]

        # 2. 指标计算
        ind = compute_indicators(data)

        # 3. 风险计算（key_support 在否决和评分之前就需要）
        key_support = compute_key_support(data, self.support_lookback_days)
        if key_support is None:
            return Strategy2Evaluation(
                passed=False,
                code=code,
                name=name,
                evaluation_date=evaluation_date,
                indicators=ind,
                status_reason="INSUFFICIENT_STRATEGY_DATA",
            )

        risk = compute_risk(
            current_close=current_close,
            key_support=key_support,
            buy_zone_max_premium=self.buy_zone_max_premium,
            stop_loss_buffer=self.stop_loss_buffer,
        )

        # 4. 一票否决检查
        # Check for big daily drops in last 5 days (for both rejection and scoring)
        has_big_drop = False
        if len(data) >= 5:
            recent_5 = data[-5:]
            for i in range(1, len(recent_5)):
                prev_close = recent_5[i - 1]["close"]
                if prev_close > 0:
                    daily_change = recent_5[i]["close"] / prev_close - 1
                    if daily_change < -0.03:
                        has_big_drop = True
                        break

        reject_reasons = check_rejection_rules(
            ind, data,
            key_support=key_support,
            current_close=current_close,
            v20=ind.v20,
        )

        # 5. 评分
        close_above_support = current_close >= key_support
        score = compute_total_score(
            ind,
            has_no_big_drop=not has_big_drop,
            close_above_support=close_above_support,
        )

        # 6. 入选条件判断
        score_ok = score.total_score >= self.candidate_min_score
        rejection_ok = len(reject_reasons) == 0
        risk_ok = risk.risk_ratio <= self.max_risk_ratio

        passed = score_ok and rejection_ok and risk_ok

        if not passed:
            status_reason = _determine_status_reason(
                score_ok, rejection_ok, risk_ok,
                reject_reasons, score.total_score, risk.risk_ratio,
            )
        else:
            status_reason = None

        return Strategy2Evaluation(
            passed=passed,
            code=code,
            name=name,
            evaluation_date=evaluation_date,
            indicators=ind,
            volume_dry_score=score.volume_dry_score,
            price_stable_score=score.price_stable_score,
            total_score=score.total_score,
            level=score.level,
            score_reasons=score.score_reasons,
            reject_reasons=reject_reasons,
            risk=risk,
            status_reason=status_reason,
        )


def _determine_status_reason(
    score_ok: bool,
    rejection_ok: bool,
    risk_ok: bool,
    reject_reasons: list[str],
    total_score: int,
    risk_ratio: float,
) -> str:
    """确定最终未入选的原因（取第一个不满足的条件）。"""
    if not rejection_ok:
        return reject_reasons[0] if reject_reasons else "REJECTION_FAILED"
    if not score_ok:
        return "SCORE_BELOW_THRESHOLD"
    if not risk_ok:
        return "RISK_RATIO_TOO_HIGH"
    return "STRATEGY2_EVALUATION_ERROR"
