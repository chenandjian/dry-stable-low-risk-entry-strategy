"""Strategy6 objective targets and execution trade plan."""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from datetime import date, timedelta

from strategy6.models import Strategy6Indicators, Strategy6Support, Strategy6TradePlan


def calculate_trade_plan(
    ind: Strategy6Indicators,
    support: Strategy6Support,
    config: dict,
    *,
    entry_archetype: str = "",
    entry_trigger_price: float | None = None,
) -> Strategy6TradePlan:
    if support.key_support_price <= 0 or support.support_zone_high <= 0:
        return Strategy6TradePlan()

    current = ind.current_price
    archetype = entry_archetype or _infer_legacy_archetype(ind, support, config)
    if archetype == "NONE":
        return Strategy6TradePlan(entry_archetype="NONE")
    if archetype == "WAIT_BREAKOUT":
        planning_entry = support.pivot_price
        suggested = None
        buy_low = planning_entry
        buy_high = planning_entry
    elif archetype == "PIVOT_BREAKOUT":
        planning_entry = current
        suggested = current
        buy_low = support.pivot_price
        buy_high = min(current * 1.01, support.pivot_price * (1 + float(config["breakout_extended_max_pct"])))
    elif archetype == "FAILED_BREAKOUT_RECLAIM":
        planning_entry = max(float(entry_trigger_price or 0.0), current)
        suggested = planning_entry
        buy_low = float(entry_trigger_price or support.support_zone_low)
        buy_high = planning_entry * 1.01
    elif archetype == "SUPPORT_PULLBACK":
        planning_entry = current
        suggested = current
    elif current > support.support_zone_high:
        planning_entry = support.support_zone_high
        suggested = support.support_zone_high
    else:
        planning_entry = current
        suggested = None
    if archetype == "SUPPORT_PULLBACK":
        if support.support_zone_low <= current <= support.support_zone_high * 1.02:
            buy_low = support.support_zone_low
            buy_high = support.support_zone_high
        else:
            tactical_width = max(
                current * float(config["support_zone_price_pct"]),
                ind.atr14 * float(config["support_zone_atr_multiplier"]),
            )
            buy_low = support.tactical_support_price - tactical_width
            buy_high = support.tactical_support_price + tactical_width

    stop = _stop_loss(ind, support, config, archetype, planning_entry)
    if planning_entry <= stop:
        return Strategy6TradePlan(
            suggested_buy_price=suggested,
            buy_zone_low=_round_price(buy_low),
            buy_zone_high=_round_price(buy_high),
            stop_loss_price=_round_price(stop),
            entry_archetype=archetype,
        )

    risk = planning_entry - stop
    signal_date, valid_from_date, valid_until_date = _valid_dates(
        ind.evaluation_date,
        int(config["buy_zone_valid_days"]),
    )
    objective_1, objective_2 = _objective_targets(ind, support, planning_entry, config)
    reward_1 = max(0.0, objective_1 - planning_entry)
    reward_2 = max(0.0, objective_2 - planning_entry)
    execution_1_5r = planning_entry + risk * 1.5
    execution_2r = planning_entry + risk * 2.0
    execution_2_5r = planning_entry + risk * 2.5
    execution_3_5r = planning_entry + risk * 3.5
    objective_rr_1 = reward_1 / risk if risk > 0 else 0.0
    objective_rr_2 = reward_2 / risk if risk > 0 else 0.0
    return Strategy6TradePlan(
        suggested_buy_price=_round_price(suggested) if suggested is not None else None,
        buy_zone_low=_round_price(buy_low),
        buy_zone_high=_round_price(buy_high),
        stop_loss_price=_round_price(stop),
        objective_target_1=_round_price(objective_1),
        objective_target_2=_round_price(objective_2),
        execution_target_1_5r=_round_price(execution_1_5r),
        execution_target_2r=_round_price(execution_2r),
        execution_target_2_5r=_round_price(execution_2_5r),
        execution_target_3_5r=_round_price(execution_3_5r),
        # Legacy aliases now expose objective targets, not manufactured R targets.
        target_price_1=_round_price(objective_1),
        target_price_2=_round_price(objective_2),
        target_price_3=_round_price(execution_3_5r),
        risk_amount=_round_price(risk),
        reward_amount_1=_round_price(reward_1),
        reward_amount_2=_round_price(reward_2),
        reward_amount_3=_round_price(execution_3_5r - planning_entry),
        risk_reward_ratio_1=round(objective_rr_1, 4),
        risk_reward_ratio_2=round(objective_rr_2, 4),
        risk_reward_ratio_3=3.5,
        objective_rr_1=round(objective_rr_1, 4),
        objective_rr_2=round(objective_rr_2, 4),
        signal_date=signal_date,
        valid_from_date=valid_from_date,
        valid_until_date=valid_until_date,
        buy_zone_valid_days=int(config["buy_zone_valid_days"]),
        suggested_limit_price=_round_price(suggested) if suggested is not None else None,
        entry_archetype=archetype,
        execution_notes=[
            "SIGNAL_AFTER_CLOSE",
            "NEXT_TRADING_DAY_ONLY",
            "DO_NOT_CHASE_ABOVE_BUY_ZONE",
            "ONE_WORD_LIMIT_UP_NO_FILL",
            "T1_STOP_UNAVAILABLE_ON_BUY_DAY",
            "LIMIT_DOWN_STOP_MAY_NOT_FILL",
            "PRICE_BASIS_FORWARD_ADJUSTED",
            "SLIPPAGE_COMMISSION_TAX_NOT_INCLUDED_IN_SIGNAL_RR",
            *(["WAIT_FOR_BREAKOUT_NO_ORDER"] if archetype == "WAIT_BREAKOUT" else []),
        ],
    )


def _stop_loss(
    ind: Strategy6Indicators,
    support: Strategy6Support,
    config: dict,
    archetype: str,
    planning_entry: float,
) -> float:
    if archetype in {"PIVOT_BREAKOUT", "WAIT_BREAKOUT"} and support.pivot_price > 0:
        return support.pivot_price - max(support.pivot_price * 0.01, ind.atr14 * 0.5)
    if archetype == "FAILED_BREAKOUT_RECLAIM":
        valid = [
            value for value in (support.tactical_support_price, support.key_support_price)
            if 0 < value < planning_entry
        ]
        reference = max(valid, default=support.key_support_price)
        return reference - max(reference * 0.01, ind.atr14 * 0.5)
    valid_supports = [
        value for value in (support.tactical_support_price, support.key_support_price)
        if 0 < value <= planning_entry
    ]
    reference = max(valid_supports, default=support.key_support_price)
    support_buffer = reference * float(config["stop_key_support_pct"])
    atr_buffer = ind.atr14 * float(config["stop_atr_multiplier"])
    return reference - max(support_buffer, atr_buffer)


def _infer_legacy_archetype(
    ind: Strategy6Indicators,
    support: Strategy6Support,
    config: dict,
) -> str:
    if (
        support.pivot_price > 0
        and support.pivot_price < ind.current_price <= support.pivot_price * (1 + float(config["breakout_extended_max_pct"]))
        and ind.current_volume_ratio_20 >= 1.3
        and ind.current_close_position >= 0.65
    ):
        return "PIVOT_BREAKOUT"
    if support.support_zone_low <= ind.current_price <= support.support_zone_high * 1.02:
        return "SUPPORT_PULLBACK"
    if support.pivot_price > ind.current_price > 0:
        return "WAIT_BREAKOUT"
    return "NONE"


def _objective_targets(
    ind: Strategy6Indicators,
    support: Strategy6Support,
    suggested: float,
    config: dict,
) -> tuple[float, float]:
    pivot = support.pivot_price
    height = support.box_height
    atr = ind.atr14
    if atr <= 0:
        return 0.0, 0.0

    pressures = [
        value for value in (
            pivot,
            ind.highest_close_20,
            ind.highest_close_120,
            ind.highest_close_250,
        )
        if value > suggested
    ]
    nearest_pressure = min(pressures) if pressures else 0.0
    if pivot <= 0 or height <= 0:
        ordered_pressures = sorted(set(pressures))
        objective_1 = ordered_pressures[0] if ordered_pressures else suggested + atr * 2
        upper_pressure = ordered_pressures[1] if len(ordered_pressures) > 1 else float("inf")
        objective_2 = min(
            upper_pressure,
            suggested + atr * 4,
            suggested * (1 + float(config["target_2_cap_pct"])),
        )
        if objective_2 == float("inf"):
            objective_2 = suggested + atr * 4
        return min(objective_1, objective_2), objective_2
    if ind.current_price < ind.highest_close_20:
        objective_1 = nearest_pressure or min(pivot + height * 0.8, suggested + atr * 3)
        objective_2 = min(
            pivot + height * 0.8,
            suggested + atr * 4,
            suggested * (1 + float(config["target_2_cap_pct"])),
        )
    elif ind.current_price >= ind.highest_close_250 > 0:
        objective_1 = min(pivot + height * 0.8, suggested + atr * 3)
        objective_2 = min(
            pivot + height,
            suggested + atr * 4,
            suggested * (1 + float(config["target_2_cap_pct"])),
        )
    else:
        objective_1 = nearest_pressure or min(pivot + height * 0.8, suggested + atr * 3)
        objective_2 = min(
            pivot + height,
            suggested + atr * 4,
            suggested * (1 + float(config["target_2_cap_pct"])),
        )
    if objective_1 <= suggested:
        objective_1 = 0.0
    if objective_2 <= suggested:
        objective_2 = 0.0
    if objective_1 > 0 and objective_2 > 0:
        objective_1 = min(objective_1, objective_2)
    return objective_1, objective_2


def _round_price(value: float) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _valid_dates(signal_date: str, valid_days: int) -> tuple[str, str, str]:
    try:
        signal = date.fromisoformat(str(signal_date)[:10])
    except ValueError:
        return str(signal_date or ""), "", ""
    valid_from = _add_weekdays(signal, 1)
    valid_until = _add_weekdays(valid_from, max(0, valid_days - 1))
    return signal.isoformat(), valid_from.isoformat(), valid_until.isoformat()


def _add_weekdays(value: date, days: int) -> date:
    current = value
    added = 0
    while added < days:
        current += timedelta(days=1)
        if current.weekday() < 5:
            added += 1
    return current
