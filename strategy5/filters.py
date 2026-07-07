"""Strategy5 hard filters and candidate classification."""
from __future__ import annotations

from strategy5.models import Strategy5Indicators, Strategy5Support


def hard_filter_reasons(ind: Strategy5Indicators, config: dict) -> list[str]:
    reasons: list[str] = []
    if ind.trading_days < config["minimum_kline_days"]:
        return ["INSUFFICIENT_KLINE_DAYS"]
    if ind.trading_days < config["minimum_trading_days"]:
        reasons.append(f"TRADING_DAYS_LT_{config['minimum_trading_days']}")
    if min(ind.ma5, ind.ma10, ind.ma20, ind.ma50, ind.ma100, ind.ma120, ind.ma250) <= 0:
        reasons.append("MA_CALC_FAILED")
    if ind.ma250 > 0 and ind.close <= ind.ma250:
        reasons.append("CLOSE_LE_MA250")
    if ind.ma120 > 0 and ind.ma250 > 0 and ind.ma120 <= ind.ma250:
        reasons.append("MA120_LE_MA250")
    if ind.avg_turnover_60d <= config["min_avg_amount_60d_yi"]:
        reasons.append("AVG60D_LE_20YI")
    if ind.avg_turnover_30d <= config["min_avg_amount_30d_yi"]:
        reasons.append("AVG30D_LE_15YI")
    if ind.avg_turnover_10d <= config["min_avg_amount_10d_yi"]:
        reasons.append("AVG10D_LE_10YI")
    if not ind.strength_trigger:
        reasons.append("SHORT_TERM_STRENGTH_FAILED")
    if not ind.high_trigger:
        reasons.append("NEW_HIGH_FAILED")
    if ind.amplitude_5d > config["max_amp_5d"]:
        reasons.append("AMP5D_GT_22PCT")
    if ind.amplitude_10d > config["max_amp_10d"]:
        reasons.append("AMP10D_GT_45PCT")
    if ind.drawdown_from_20d_high < config["max_drawdown_20d"]:
        reasons.append("DRAWDOWN_GT_30PCT")
    if ind.max_decline_5d < config["max_decline_5d"]:
        reasons.append("MAX_DECLINE_LT_NEG8PCT")
    if ind.has_volume_up_decline:
        reasons.append("CONSOLIDATION_VOLUME_UP_DECLINE")
    if ind.ma50 > 0 and ind.close < ind.ma50 * config["ma50_min_ratio"]:
        reasons.append("CLOSE_LT_MA50_0_92")
    return reasons


def classify_candidate(
    ind: Strategy5Indicators,
    support: Strategy5Support,
    config: dict,
    reject_reasons: list[str],
) -> tuple[str, str]:
    if reject_reasons:
        return "REJECTED", "rejected"
    if support.support_status == "SPRINT_FAILED":
        return "REJECTED", "rejected"
    if support.support_status in {"SPRINT_MA5_SUPPORT", "SPRINT_MA10_SUPPORT", "SPRINT_MA20_SUPPORT"}:
        if "BIG_DROP_TODAY" not in ind.risk_tags and support.support_score >= config["key_candidate_min_support_score"]:
            return "KEY_CANDIDATE", "highlight"
    if support.support_status == "SPRINT_MA50_TESTING":
        return "WATCH_CANDIDATE", "observe"
    if support.support_status == "SPRINT_MA20_SUPPORT" and (ind.daily_return <= -0.07 or support.support_score < 8):
        return "WATCH_CANDIDATE", "observe"
    if 0.18 < ind.amplitude_5d <= config["max_amp_5d"]:
        return "WATCH_CANDIDATE", "observe"
    if 0.35 < ind.amplitude_10d <= config["max_amp_10d"]:
        return "WATCH_CANDIDATE", "observe"
    if config["max_drawdown_20d"] < ind.drawdown_from_20d_high <= -0.22:
        return "WATCH_CANDIDATE", "observe"
    return "REJECTED", "rejected"
