"""策略3唯一评估入口。"""
from strategy3.indicators import compute_indicators
from strategy3.models import Strategy3Evaluation
from strategy3.pullback import evaluate_pullback
from strategy3.risk import compute_strategy3_risk
from strategy3.scorer import build_strategy3_score, determine_status_reason
from strategy3.second_breakout import evaluate_second_breakout
from strategy3.trend import evaluate_trend
from strategy3.validation import (
    resolve_strategy3_config,
    validate_ohlc_structure,
    validate_ohlc_values,
)
from strategy3.volume_stability import evaluate_volume_stability


class StrongPullbackSecondBreakoutEngine:
    """策略3「强势回踩二次启动」唯一判断入口。"""

    def __init__(self, config: dict):
        self.config = resolve_strategy3_config(config)
        self.strategy_window_days = self.config["strategy_window_days"]
        self.minimum_required_days = self.config["minimum_required_days"]

    def evaluate_at(
        self,
        data: list[dict],
        *,
        code: str = "",
        name: str = "",
        market_data: list[dict] | None = None,
    ) -> Strategy3Evaluation:
        struct_error = validate_ohlc_structure(data)
        if struct_error:
            return Strategy3Evaluation(False, code=code, name=name, status_reason=struct_error)

        strategy_data = data[-self.strategy_window_days:] if len(data) > self.strategy_window_days else data
        value_error = validate_ohlc_values(strategy_data)
        if value_error:
            return Strategy3Evaluation(False, code=code, name=name, status_reason=value_error)
        if len(strategy_data) < self.minimum_required_days:
            return Strategy3Evaluation(
                False,
                code=code,
                name=name,
                evaluation_date=strategy_data[-1]["date"] if strategy_data else "",
                status_reason="INSUFFICIENT_STRATEGY_DATA",
            )

        evaluation_date = strategy_data[-1]["date"]
        ind = compute_indicators(strategy_data, self.config, market_data=market_data)

        reject_reasons: list[str] = []
        score_reasons: list[str] = []

        trend_rejects, trend_score, trend_reasons = evaluate_trend(ind, self.config)
        pullback_rejects, pullback_score, pullback_reasons = evaluate_pullback(ind, strategy_data, self.config)
        volume_rejects, volume_score, volume_reasons = evaluate_volume_stability(ind, strategy_data, self.config)
        breakout_rejects, breakout_score, breakout_reasons = evaluate_second_breakout(ind, strategy_data, self.config)
        risk, risk_rejects, risk_score, risk_reasons = compute_strategy3_risk(strategy_data, ind, self.config)

        reject_reasons.extend(trend_rejects)
        reject_reasons.extend(pullback_rejects)
        reject_reasons.extend(volume_rejects)
        reject_reasons.extend(breakout_rejects)
        reject_reasons.extend(risk_rejects)
        for prefix, reasons in (
            ("trend", trend_reasons),
            ("pullback", pullback_reasons),
            ("volume", volume_reasons),
            ("second_breakout", breakout_reasons),
            ("risk", risk_reasons),
        ):
            score_reasons.extend([f"{prefix}:{reason}" for reason in reasons])

        score = build_strategy3_score(
            trend_score=trend_score,
            pullback_score=pullback_score,
            volume_stability_score=volume_score,
            second_breakout_score=breakout_score,
            risk_reward_score=risk_score,
            score_reasons=score_reasons,
            config=self.config,
        )
        status_reason = determine_status_reason(reject_reasons, score.total_score, self.config)
        passed = status_reason is None and risk.risk_ratio <= self.config["max_risk_ratio"] and risk.rr1 >= 1.5

        return Strategy3Evaluation(
            passed=passed,
            code=code,
            name=name,
            evaluation_date=evaluation_date,
            indicators=ind,
            risk=risk,
            trend_score=score.trend_score,
            pullback_score=score.pullback_score,
            volume_stability_score=score.volume_stability_score,
            second_breakout_score=score.second_breakout_score,
            risk_reward_score=score.risk_reward_score,
            total_score=score.total_score,
            level=score.level,
            current_close=ind.current_close,
            score_reasons=score.score_reasons,
            reject_reasons=reject_reasons,
            status_reason=status_reason,
        )
