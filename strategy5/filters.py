"""Strategy5 hard filters and candidate classification."""
from __future__ import annotations

from strategy5.models import Strategy5Indicators, Strategy5Support, Strategy5VolumeDry


def hard_filter_reasons(
    ind: Strategy5Indicators,
    config: dict,
    volume_dry: Strategy5VolumeDry | None = None,
    *,
    code: str = "",
) -> list[str]:
    reasons: list[str] = []
    if ind.trading_days < config["minimum_trading_days"]:
        reasons.append(f"TRADING_DAYS_LT_{config['minimum_trading_days']}")
    if min(ind.ma5, ind.ma10, ind.ma20, ind.ma50, ind.ma100, ind.ma120, ind.ma250) <= 0:
        reasons.append("MA_CALC_FAILED")
    if ind.ma250 > 0 and ind.close <= ind.ma250:
        reasons.append("CLOSE_LE_MA250")
    if ind.ma120 > 0 and ind.ma250 > 0 and ind.ma120 <= ind.ma250:
        reasons.append("MA120_LE_MA250")
    liquidity = _liquidity_thresholds_for_code(config, code)
    reason_prefix = "KCB_" if _is_kcb_code(code) else ""
    if ind.avg_turnover_60d <= liquidity["min_avg_amount_60d_yi"]:
        reasons.append(f"{reason_prefix}AVG60D_LE_MIN")
    if ind.avg_turnover_30d <= liquidity["min_avg_amount_30d_yi"]:
        reasons.append(f"{reason_prefix}AVG30D_LE_MIN")
    if ind.avg_turnover_10d <= liquidity["min_avg_amount_10d_yi"]:
        reasons.append(f"{reason_prefix}AVG10D_LE_MIN")
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
    if volume_dry:
        reasons.extend(volume_dry.volume_dry_rejects)
    if ind.ma50 > 0 and ind.close < ind.ma50 * config["ma50_min_ratio"]:
        reasons.append("CLOSE_LT_MA50_0_92")
    return reasons


def _is_kcb_code(code: str) -> bool:
    normalized = str(code or "").strip()
    return normalized.startswith(("688", "689"))


def _liquidity_thresholds_for_code(config: dict, code: str) -> dict[str, float]:
    if _is_kcb_code(code):
        return {
            "min_avg_amount_60d_yi": config["kcb_min_avg_amount_60d_yi"],
            "min_avg_amount_30d_yi": config["kcb_min_avg_amount_30d_yi"],
            "min_avg_amount_10d_yi": config["kcb_min_avg_amount_10d_yi"],
        }
    return {
        "min_avg_amount_60d_yi": config["min_avg_amount_60d_yi"],
        "min_avg_amount_30d_yi": config["min_avg_amount_30d_yi"],
        "min_avg_amount_10d_yi": config["min_avg_amount_10d_yi"],
    }


def classify_candidate(
    ind: Strategy5Indicators,
    support: Strategy5Support,
    config: dict,
    reject_reasons: list[str],
    volume_dry: Strategy5VolumeDry | None = None,
    *,
    total_score: float | None = None,
) -> tuple[str, str]:
    if reject_reasons:
        return "REJECTED", "rejected"
    if support.support_status == "SPRINT_FAILED":
        return "REJECTED", "rejected"
    volume_score = volume_dry.volume_dry_score if volume_dry else 0
    if _is_trade_candidate(ind, support, config, volume_score, total_score):
        return "BUY_CANDIDATE", "trade"
    if support.support_status in {"SPRINT_MA5_SUPPORT", "SPRINT_MA10_SUPPORT", "SPRINT_MA20_SUPPORT"}:
        if (
            "BIG_DROP_TODAY" not in ind.risk_tags
            and support.support_score >= config["key_candidate_min_support_score"]
            and volume_score >= config["volume_dry_min_score_key"]
        ):
            return "WATCH_CANDIDATE", "observe"
        if volume_score < config["volume_dry_min_score_watch"]:
            return "REJECTED", "rejected"
    if support.support_status == "SPRINT_MA50_TESTING":
        if volume_score < config["volume_dry_min_score_watch"]:
            return "REJECTED", "rejected"
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


def _is_trade_candidate(
    ind: Strategy5Indicators,
    support: Strategy5Support,
    config: dict,
    volume_score: int,
    total_score: float | None,
) -> bool:
    if total_score is None or total_score < config["trade_candidate_min_score"]:
        return False
    if volume_score < config["trade_volume_dry_min_score"]:
        return False
    if not config["trade_allow_ret50"] and ind.strength_trigger == "ret_50d":
        return False
    if not config["trade_allow_ma5_support"] and support.support_status == "SPRINT_MA5_SUPPORT":
        return False
    return support.support_status in {"SPRINT_MA10_SUPPORT", "SPRINT_MA20_SUPPORT"}
