"""Strategy6 trade plan calculation."""
from __future__ import annotations

from strategy6.models import Strategy6Indicators, Strategy6Support, Strategy6TradePlan


def calculate_trade_plan(ind: Strategy6Indicators, support: Strategy6Support) -> Strategy6TradePlan:
    if support.key_support_price <= 0 or support.support_zone_high <= 0:
        return Strategy6TradePlan()

    current = ind.current_price
    if support.support_zone_low <= current <= support.support_zone_high:
        suggested = current
    elif current > support.support_zone_high:
        suggested = support.support_zone_high
    else:
        suggested = None

    stop = _stop_loss(support)
    buy_low = support.support_zone_low
    buy_high = support.support_zone_high
    if suggested is None or suggested <= stop:
        return Strategy6TradePlan(
            suggested_buy_price=suggested,
            buy_zone_low=round(buy_low, 4),
            buy_zone_high=round(buy_high, 4),
            stop_loss_price=round(stop, 4),
        )

    risk = suggested - stop
    target1, target2, target3 = _targets(ind, support, suggested, risk)
    reward1 = target1 - suggested
    reward2 = target2 - suggested
    reward3 = target3 - suggested
    return Strategy6TradePlan(
        suggested_buy_price=round(suggested, 4),
        buy_zone_low=round(buy_low, 4),
        buy_zone_high=round(buy_high, 4),
        stop_loss_price=round(stop, 4),
        target_price_1=round(target1, 4),
        target_price_2=round(target2, 4),
        target_price_3=round(target3, 4),
        risk_amount=round(risk, 4),
        reward_amount_1=round(reward1, 4),
        reward_amount_2=round(reward2, 4),
        reward_amount_3=round(reward3, 4),
        risk_reward_ratio_1=round(reward1 / risk, 4) if risk > 0 else 0.0,
        risk_reward_ratio_2=round(reward2 / risk, 4) if risk > 0 else 0.0,
        risk_reward_ratio_3=round(reward3 / risk, 4) if risk > 0 else 0.0,
    )


def _stop_loss(support: Strategy6Support) -> float:
    if support.support_status in {"MA5_SUPPORT", "MA10_SUPPORT"}:
        return support.key_support_price * 0.97
    if support.support_status == "MA20_SUPPORT":
        return support.key_support_price * 0.95
    if support.support_status == "MA50_TESTING":
        return support.key_support_price * 0.92
    return support.key_support_price * 0.96


def _targets(ind: Strategy6Indicators, support: Strategy6Support, suggested: float, risk: float) -> tuple[float, float, float]:
    pivot = max(support.pivot_price, suggested)
    box_height = max(support.box_height, risk)
    if ind.current_price < ind.highest_close_20:
        target1 = max(ind.highest_close_20, suggested + risk * 1.5)
        target2 = max(pivot + box_height * 0.8, suggested + risk * 2.0)
        target3 = max(pivot + box_height * 1.2, suggested + risk * 3.0)
    elif ind.current_price >= ind.highest_close_250 > 0:
        target1 = suggested + risk * 1.5
        target2 = suggested + risk * 2.5
        target3 = suggested + risk * 3.5
    else:
        target1 = suggested + risk * 1.5
        target2 = max(pivot + box_height, suggested + risk * 2.5)
        target3 = max(pivot + box_height * 1.5, suggested + risk * 3.5)
    return target1, min(target2, suggested * 1.35), min(target3, suggested * 1.50)

