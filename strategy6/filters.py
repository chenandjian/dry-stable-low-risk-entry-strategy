"""Strategy6 hard filters and candidate classification."""
from __future__ import annotations

from strategy6.models import (
    Strategy6DryTail,
    Strategy6Indicators,
    Strategy6Score,
    Strategy6Start,
    Strategy6Support,
    Strategy6TradePlan,
)
from strategy6.strong_start import PASSING_START_TYPES


def hard_filter_reasons(
    ind: Strategy6Indicators,
    start: Strategy6Start,
    support: Strategy6Support,
    dry_tail: Strategy6DryTail,
    trade_plan: Strategy6TradePlan,
    config: dict,
) -> list[str]:
    reasons: list[str] = []
    if ind.trading_days < config["minimum_trading_days"]:
        reasons.append(f"TRADING_DAYS_LT_{config['minimum_trading_days']}")
    if min(ind.ma5, ind.ma10, ind.ma20, ind.ma50, ind.ma120, ind.ma250) <= 0:
        reasons.append("MA_CALC_FAILED")
    if ind.ma250 > 0 and ind.current_price <= ind.ma250:
        reasons.append("CLOSE_LE_MA250")
    if ind.ma120 > 0 and ind.ma250 > 0 and ind.ma120 <= ind.ma250:
        reasons.append("MA120_LE_MA250")
    if ind.amount_avg_60 < config["min_avg_amount_60d_yi"]:
        reasons.append("AVG60D_LT_MIN")
    if ind.amount_avg_30 < config["min_avg_amount_30d_yi"]:
        reasons.append("AVG30D_LT_MIN")
    if ind.amount_avg_10 < config["min_avg_amount_10d_yi"]:
        reasons.append("AVG10D_LT_MIN")
    if ind.amount_avg_30 > 0 and ind.amount_avg_10 < ind.amount_avg_30 * config["amount10_vs_30_min_ratio"]:
        reasons.append("AVG10D_LT_AVG30D_RATIO")
    if ind.relative_strength_20_observed and ind.relative_strength_20 < config["min_relative_strength_20"]:
        threshold = str(config["min_relative_strength_20"]).replace(".", "_")
        reasons.append(f"RS20_LT_{threshold}")
    if start.start_type not in PASSING_START_TYPES:
        reasons.append("NO_STRONG_START")
    if not start.high_trigger:
        reasons.append("NO_NEW_HIGH_CONFIRMATION")
    if support.support_status == "SUPPORT_FAILED":
        reasons.append("SUPPORT_FAILED")
    if ind.ma50 > 0 and ind.current_price < ind.ma50 * config["ma50_min_ratio"]:
        reasons.append("CLOSE_LT_MA50_0_92")
    reasons.extend(dry_tail.rejects)
    if trade_plan.risk_reward_ratio_2 < config["rr2_min_watch"]:
        threshold = str(config["rr2_min_watch"]).replace(".", "_")
        reasons.append(f"RR2_LT_{threshold}")
    return _dedupe(reasons)


def classify_candidate(
    ind: Strategy6Indicators,
    start: Strategy6Start,
    support: Strategy6Support,
    dry_tail: Strategy6DryTail,
    trade_plan: Strategy6TradePlan,
    score: Strategy6Score,
    reject_reasons: list[str],
    config: dict,
) -> tuple[str, str, str, str]:
    lifecycle = _lifecycle_status(ind, support, dry_tail, trade_plan, reject_reasons)
    if reject_reasons:
        return "REJECTED", "rejected", lifecycle, "排除：存在硬性风险或盈亏比不足"
    major_risk = any(tag in ind.risk_tags for tag in {"BIG_DOWN_VOLUME"})
    environment_blocks_ready = _environment_blocks_ready(ind)
    if (
        score.total_score >= config["ready_min_score"]
        and trade_plan.risk_reward_ratio_2 >= config["rr2_min_ready"]
        and support.support_zone_low <= ind.current_price <= support.support_zone_high
        and ind.volume_ratio_5_20 <= config["tail_strong_volume_ratio_5_20"]
        and support.support_status in {"MA5_SUPPORT", "MA10_SUPPORT", "MA20_SUPPORT"}
        and not major_risk
        and not environment_blocks_ready
    ):
        return "READY_CANDIDATE", "ready", lifecycle, "低吸候选：支撑区内，量干价稳，盈亏比较好"
    if (
        score.total_score >= config["key_min_score"]
        and trade_plan.risk_reward_ratio_2 >= config["rr2_min_key"]
        and support.support_status in {"MA5_SUPPORT", "MA10_SUPPORT", "MA20_SUPPORT"}
        and dry_tail.dry_stable_score >= 15
        and not major_risk
        and not environment_blocks_ready
    ):
        return "KEY_CANDIDATE", "highlight", lifecycle, "重点观察：等待支撑低吸或突破确认"
    if score.total_score >= config["watch_min_score"] or trade_plan.risk_reward_ratio_2 >= config["rr2_min_watch"]:
        return "WATCH_CANDIDATE", "observe", lifecycle, "观察：形态部分满足，等待进一步确认"
    return "REJECTED", "rejected", lifecycle, "排除：评分不足"


def _lifecycle_status(
    ind: Strategy6Indicators,
    support: Strategy6Support,
    dry_tail: Strategy6DryTail,
    trade_plan: Strategy6TradePlan,
    reject_reasons: list[str],
) -> str:
    if reject_reasons and ("BIG_DOWN_VOLUME" in reject_reasons or "SUPPORT_FAILED" in reject_reasons):
        return "FAILED"
    if trade_plan.suggested_buy_price and ind.current_price > support.pivot_price * 1.08:
        return "EXTENDED"
    if support.pivot_price > 0 and ind.current_price > support.pivot_price and ind.volume_ratio_5_20 >= 1.3:
        return "BREAKOUT_CONFIRMED"
    if trade_plan.suggested_buy_price and support.support_zone_low <= ind.current_price <= support.support_zone_high:
        return "BUY_ZONE"
    if dry_tail.dry_tail_pass:
        return "READY"
    return "SETUP_FORMING"


def _environment_blocks_ready(ind: Strategy6Indicators) -> bool:
    if ind.market_filter_enabled and ind.market_filter_mode in {"strict", "downgrade"}:
        if ind.market_status in {"MARKET_WEAK", "MARKET_RISK"}:
            if ind.market_filter_mode == "strict":
                ind.warn_tags.append("MARKET_WEAK_STRICT")
            else:
                ind.warn_tags.append("MARKET_WEAK_DOWNGRADED")
            return True
    if ind.sector_filter_enabled and ind.sector_filter_mode in {"strict", "downgrade"}:
        if ind.sector_strength_status in {"SECTOR_WEAK", "SECTOR_RISK"}:
            if ind.sector_filter_mode == "strict":
                ind.warn_tags.append("SECTOR_WEAK_STRICT")
            else:
                ind.warn_tags.append("SECTOR_WEAK_DOWNGRADED")
            return True
    return False


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
