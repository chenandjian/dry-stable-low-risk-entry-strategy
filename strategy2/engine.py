# strategy2/engine.py
"""策略2唯一评估入口 — ExtremeDryStableStrategyEngine。

组合指标、评分、否决、风险模块，输出最终评估结果。
策略窗口裁剪的唯一执行点。不依赖策略1的任何模块。
"""
import logging
from strategy2.models import (
    Strategy2Indicators,
    Strategy2Score,
    Strategy2Risk,
    Strategy2Evaluation,
)
from strategy2.indicators import compute_indicators
from strategy2.scorer import compute_total_score
from strategy2.rejection import check_rejection_rules
from strategy2.risk import compute_key_support, compute_risk
from strategy2.trend import evaluate_trend
from strategy2.validation import (
    resolve_strategy2_config,
    validate_ohlc_structure,
    validate_ohlc_values,
    recent_daily_changes,
)

logger = logging.getLogger(__name__)


class ExtremeDryStableStrategyEngine:
    """策略2「极致量干价稳」唯一评估入口。

    使用方法:
        engine = ExtremeDryStableStrategyEngine(strategy2_config)
        evaluation = engine.evaluate_at(data, code="000001", name="平安银行")
    """

    def __init__(self, config: dict):
        """初始化并校验策略2配置。

        config 可以是独立的 strategy2 配置字典，也可以包含
        strategy2/liquidity 段（调用 resolve_strategy2_config）。
        始终通过 resolve_strategy2_config 校验，确保跨入口一致性。
        """
        # 始终通过统一校验器：确保所有 entry point 配置行为一致
        resolved = resolve_strategy2_config(config)

        self.strategy_window_days = resolved["strategy_window_days"]
        self.min_required = resolved["minimum_required_days"]
        self.candidate_min_score = resolved["candidate_min_score"]
        self.max_risk_ratio = resolved["max_risk_ratio"]
        self.support_lookback_days = resolved["support_lookback_days"]
        self.buy_zone_max_premium = resolved["buy_zone_max_premium"]
        self.stop_loss_buffer = resolved["stop_loss_buffer"]

    def evaluate_at(
        self,
        data: list[dict],
        *,
        code: str = "",
        name: str = "",
    ) -> Strategy2Evaluation:
        """对单只股票在评估日执行完整策略2评估。

        评估顺序（按设计文档）：
        1. 完整行情校验 (BUG-S2-005)
        2. 策略窗口截取 (BUG-S2-002)
        3. 最低有效数据检查
        4. V20=0 排除 (BUG-S2-004)
        5. 指标、风险、否决、评分

        Args:
            data: 日线数据（按日期升序）。可包含策略窗口外的数据。
            code: 股票代码。
            name: 股票名称。

        Returns:
            Strategy2Evaluation — passed=True 表示满足所有入选条件。
        """
        # 1. 结构校验 — 日期格式/排序/字段存在（RECHECK-S2-004/007）
        if not data or not isinstance(data, list):
            return Strategy2Evaluation(
                passed=False, code=code, name=name,
                evaluation_date="",
                status_reason="INVALID_MARKET_DATA",
            )
        struct_error = validate_ohlc_structure(data)
        if struct_error is not None:
            return Strategy2Evaluation(
                passed=False, code=code, name=name,
                evaluation_date="",
                status_reason=struct_error,
            )

        # 2. 策略窗口截取 — 唯一裁剪点
        if len(data) > self.strategy_window_days:
            strategy_data = data[-self.strategy_window_days:]
        else:
            strategy_data = data

        # 3. 窗口内值校验 — OHLC 数值和关系（RECHECK-S2-004）
        values_error = validate_ohlc_values(strategy_data)
        if values_error is not None:
            return Strategy2Evaluation(
                passed=False, code=code, name=name,
                evaluation_date="",
                status_reason=values_error,
            )

        # 4. 最低有效数据检查
        if len(strategy_data) < self.min_required:
            return Strategy2Evaluation(
                passed=False, code=code, name=name,
                evaluation_date=strategy_data[-1]["date"],
                status_reason="INSUFFICIENT_STRATEGY_DATA",
            )

        evaluation_date = strategy_data[-1]["date"]
        current_close = strategy_data[-1]["close"]

        # 5. 指标计算
        ind = compute_indicators(strategy_data)

        # 6. V20=0 排除
        if ind.v20 <= 0:
            return Strategy2Evaluation(
                passed=False, code=code, name=name,
                evaluation_date=evaluation_date,
                indicators=ind,
                status_reason="INVALID_MARKET_DATA",
            )

        # 7. 走势趋势过滤 — 在量干价稳评分、风险计算和一票否决之前执行
        trend = evaluate_trend(strategy_data)
        if trend is None:
            return Strategy2Evaluation(
                passed=False, code=code, name=name,
                evaluation_date=evaluation_date,
                indicators=ind,
                status_reason="INSUFFICIENT_STRATEGY_DATA",
            )
        if trend.trend_type in ("INVALID_MARKET_DATA", "INSUFFICIENT_TREND_DATA"):
            return Strategy2Evaluation(
                passed=False, code=code, name=name,
                evaluation_date=evaluation_date,
                indicators=ind,
                trend=trend,
                status_reason=trend.trend_type,
            )
        if trend.trend_type == "DOWNTREND":
            return Strategy2Evaluation(
                passed=False, code=code, name=name,
                evaluation_date=evaluation_date,
                indicators=ind,
                trend=trend,
                current_close=current_close,
                status_reason="DOWNTREND_FILTERED",
            )

        # 8. 风险计算
        key_support = compute_key_support(strategy_data, self.support_lookback_days)
        if key_support is None:
            return Strategy2Evaluation(
                passed=False, code=code, name=name,
                evaluation_date=evaluation_date,
                indicators=ind,
                trend=trend,
                status_reason="INSUFFICIENT_STRATEGY_DATA",
            )

        risk = compute_risk(
            current_close=current_close,
            key_support=key_support,
            buy_zone_max_premium=self.buy_zone_max_premium,
            stop_loss_buffer=self.stop_loss_buffer,
        )

        # 9. 最近5日涨跌
        changes_5 = recent_daily_changes(strategy_data, days=5)
        has_big_drop = any(ch["change"] < -0.03 for ch in changes_5)

        # 10. 一票否决
        reject_reasons = check_rejection_rules(
            ind, strategy_data,
            key_support=key_support,
            current_close=current_close,
            v20=ind.v20,
            daily_changes=changes_5,
        )

        # 11. 评分
        close_above_support = current_close >= key_support
        score = compute_total_score(
            ind,
            has_no_big_drop=not has_big_drop,
            close_above_support=close_above_support,
        )

        # 12. 入选条件判断
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
            trend=trend,
            current_close=current_close,
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
