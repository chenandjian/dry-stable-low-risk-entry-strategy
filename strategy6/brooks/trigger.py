"""Deterministic as-of-date Brooks trade-trigger reconstruction."""
from __future__ import annotations

from datetime import date, timedelta

from strategy6.brooks.models import BrooksTailResult, BrooksTradeTriggerResult
from strategy6.models import Strategy6Support


def evaluate_brooks_trade_trigger(
    rows: list[dict],
    tail: BrooksTailResult,
    support: Strategy6Support,
    *,
    start_grade: str,
    atr14: float,
    config: dict,
) -> BrooksTradeTriggerResult:
    result = BrooksTradeTriggerResult()
    cfg = config["trade_trigger"]
    if not cfg["enabled"] or not tail.enabled or not tail.passed or not rows:
        return result
    if start_grade == "B":
        result.risk_tags.append("BROOKS_GRADE_B_WATCH_ONLY")
        return result
    if tail.compact_structure.structure_type == "BARB_WIRE":
        result.risk_tags.append("BARB_WIRE_RISK")
        return result
    current_close = float(rows[-1].get("close") or 0)
    if support.key_support_price > 0 and current_close < support.key_support_price * (
        1 - float(config["support"]["effective_break_pct"])
    ):
        result.risk_tags.append("BROOKS_SUPPORT_EFFECTIVELY_BROKEN")
        return result

    structure = tail.structure
    if structure.second_entry_long_ready and structure.second_entry_signal_date:
        _evaluate_second_entry(rows, structure.second_entry_signal_date, structure.second_entry_trigger_price, atr14, cfg, result)
    if not result.ready and structure.failed_bear_breakout:
        _evaluate_failed_breakout(rows, support, atr14, cfg, result)
    if not result.ready and support.pivot_price > 0:
        _evaluate_breakout(rows, float(support.pivot_price), atr14, cfg, result)
    return result


def _evaluate_second_entry(
    rows: list[dict],
    signal_date: str,
    trigger_price: float | None,
    atr14: float,
    config: dict,
    result: BrooksTradeTriggerResult,
) -> None:
    signal_index = next(
        (index for index, row in enumerate(rows) if str(row.get("date") or "") == signal_date),
        -1,
    )
    if signal_index < 0 or not trigger_price:
        result.risk_tags.append("BROOKS_TRIGGER_SIGNAL_NOT_VISIBLE")
        return
    valid_days = int(config["trigger_valid_days"])
    result.trigger_price = float(trigger_price)
    result.trigger_valid_until = _add_weekdays(signal_date, valid_days)
    current_index = len(rows) - 1
    if current_index > signal_index + valid_days:
        result.risk_tags.append("BROOKS_TRIGGER_EXPIRED")
        return
    if signal_index == current_index:
        result.risk_tags.append("BROOKS_TRIGGER_REQUIRES_LATER_SESSION")
        return
    last_valid_index = min(current_index, signal_index + valid_days)
    max_distance = float(atr14) * float(config["max_trigger_distance_atr"])
    for row in rows[signal_index + 1:last_valid_index + 1]:
        high = float(row.get("high") or 0)
        open_price = float(row.get("open") or 0)
        if open_price > float(trigger_price) + max_distance:
            result.risk_tags.append("BROOKS_TRIGGER_GAP_TOO_FAR")
            continue
        if high > float(trigger_price) and high - float(trigger_price) <= max_distance:
            result.ready = True
            result.second_entry_triggered = True
            result.trigger_type = "BROOKS_SUPPORT_READY"
            result.reasons.append("BROOKS_SECOND_ENTRY_TRIGGERED")
            return


def _evaluate_failed_breakout(
    rows: list[dict],
    support: Strategy6Support,
    atr14: float,
    config: dict,
    result: BrooksTradeTriggerResult,
) -> None:
    if len(rows) < 2 or support.key_support_price <= 0:
        return
    key = float(support.key_support_price)
    max_distance = float(atr14) * float(config["max_trigger_distance_atr"])
    for index in range(max(0, len(rows) - int(config["trigger_valid_days"]) - 2), len(rows) - 1):
        row = rows[index]
        if float(row.get("low") or 0) >= key or float(row.get("close") or 0) < key:
            continue
        reclaim_high = float(row.get("high") or 0)
        for following in rows[index + 1:index + int(config["trigger_valid_days"]) + 1]:
            if 0 < float(following.get("high") or 0) - reclaim_high <= max_distance:
                result.ready = True
                result.failed_bear_breakout_confirmed = True
                result.trigger_type = "BROOKS_FAILED_BREAKOUT_READY"
                result.trigger_price = reclaim_high
                result.trigger_valid_until = _add_weekdays(
                    str(row.get("date") or ""),
                    int(config["trigger_valid_days"]),
                )
                result.reasons.append("BROOKS_FAILED_BREAKOUT_CONFIRMED")
                return


def _evaluate_breakout(
    rows: list[dict],
    pivot: float,
    atr14: float,
    config: dict,
    result: BrooksTradeTriggerResult,
) -> None:
    if len(rows) < 2:
        return
    breakout_index = next(
        (
            index
            for index in range(len(rows) - 1, 0, -1)
            if float(rows[index - 1].get("close") or 0) <= pivot
            and float(rows[index].get("close") or 0) > pivot
        ),
        -1,
    )
    if breakout_index < 0:
        return

    follow_through_days = int(config["breakout_follow_through_days"])
    breakout = rows[breakout_index]
    result.trigger_price = pivot
    result.trigger_valid_until = _add_weekdays(
        str(breakout.get("date") or ""),
        follow_through_days,
    )
    elapsed_bars = len(rows) - 1 - breakout_index
    if elapsed_bars <= 0:
        result.risk_tags.append("BROOKS_BREAKOUT_REQUIRES_FOLLOW_THROUGH")
        return
    if elapsed_bars > follow_through_days:
        result.risk_tags.append("BROOKS_BREAKOUT_FOLLOW_THROUGH_EXPIRED")
        return

    current = rows[-1]
    distance = float(current.get("close") or 0) - pivot
    if float(current.get("close") or 0) >= pivot and 0 <= distance <= atr14 * float(config["max_trigger_distance_atr"]):
        result.ready = True
        result.breakout_follow_through_pass = True
        result.trigger_type = "BROOKS_BREAKOUT_READY"
        result.reasons.append("BROOKS_BREAKOUT_FOLLOW_THROUGH")


def _add_weekdays(value: str, count: int) -> str:
    try:
        current = date.fromisoformat(value[:10])
    except (TypeError, ValueError):
        return ""
    remaining = count
    while remaining:
        current += timedelta(days=1)
        if current.weekday() < 5:
            remaining -= 1
    return current.isoformat()
