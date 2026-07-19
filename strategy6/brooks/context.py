"""Bull and bear context classification for the Strategy6 Brooks path."""
from __future__ import annotations

from strategy6.brooks.models import BrooksContextResult
from strategy6.models import Strategy6Indicators, Strategy6Start, Strategy6Support


def analyze_brooks_context(
    rows: list[dict],
    indicators: Strategy6Indicators,
    start: Strategy6Start,
    support: Strategy6Support,
    config: dict,
) -> BrooksContextResult:
    cfg = config["context"]
    result = BrooksContextResult()
    if not rows or indicators.current_price <= 0 or start.start_low <= 0:
        result.risk_tags.append("BROOKS_CONTEXT_DATA_INSUFFICIENT")
        return result

    lookback = rows[-int(cfg["lower_high_low_window_days"]):]
    lower_high_flags = [
        float(current.get("high") or 0) < float(previous.get("high") or 0)
        for previous, current in zip(lookback[:-1], lookback[1:])
    ]
    lower_low_flags = [
        float(current.get("low") or 0) < float(previous.get("low") or 0)
        for previous, current in zip(lookback[:-1], lookback[1:])
    ]
    result.lower_high_count = sum(lower_high_flags)
    result.lower_low_count = sum(lower_low_flags)
    result.lower_high_low_sequence_count = _max_true_run([
        high and low for high, low in zip(lower_high_flags, lower_low_flags)
    ])
    result.ma20_slope = _moving_average_slope(
        rows,
        period=20,
        window=int(cfg["ma20_slope_window_days"]),
    )

    support_broken = support_effectively_broken(
        rows,
        support,
        float(config["support"]["effective_break_pct"]),
        int(config["support"]["consecutive_close_break_days"]),
    )
    if support_broken:
        result.risk_tags.append("BROOKS_SUPPORT_EFFECTIVELY_BROKEN")

    allowed_grade = start.start_grade in set(cfg["allowed_start_grades"])
    result.watch_only = bool(
        start.start_grade == "B" and cfg["allow_grade_b_watch_only"]
    )
    grade_pass = allowed_grade or result.watch_only
    above_start_low = indicators.current_price >= start.start_low
    ma20_floor = indicators.ma20 - indicators.atr14 * float(cfg["close_below_ma20_atr_tolerance"])
    above_ma20_floor = indicators.current_price >= ma20_floor
    trend_pass = (
        indicators.ma20 >= indicators.ma50
        or (not cfg["require_ma20_above_ma50"] and result.ma20_slope > 0)
    )
    if cfg["require_ma20_slope_positive"]:
        trend_pass = trend_pass and result.ma20_slope > 0
    sequence_pass = result.lower_high_low_sequence_count <= int(cfg["max_lower_high_low_sequence"])

    result.passed = all((
        grade_pass,
        above_start_low,
        above_ma20_floor,
        trend_pass,
        sequence_pass,
        not support_broken,
    ))
    if result.passed:
        result.context_type = "WEAK_BULL_CONTEXT" if result.watch_only else "BULL_CONTEXT"
        result.reasons.append("BROOKS_BULL_CONTEXT_VALID")
    elif (
        indicators.current_price < indicators.ma20
        and indicators.current_price < indicators.ma50
        and result.ma20_slope <= 0
        and not sequence_pass
    ):
        result.context_type = "BEAR_CONTEXT"
        result.risk_tags.append("BROOKS_BEAR_CONTEXT")
    else:
        result.context_type = "TRADING_RANGE_CONTEXT"
        result.risk_tags.append("BROOKS_CONTEXT_NOT_BULLISH")
    return result


def support_effectively_broken(
    rows: list[dict],
    support: Strategy6Support,
    effective_break_pct: float,
    consecutive_days: int,
) -> bool:
    if not rows:
        return True
    current = float(rows[-1].get("close") or 0)
    key_support = float(support.key_support_price or 0)
    defense = float(support.defense_support_price or 0)
    if defense > 0 and current < defense:
        return True
    if key_support <= 0:
        return True
    if current < key_support * (1 - effective_break_pct):
        return True
    recent = rows[-consecutive_days:]
    return len(recent) == consecutive_days and all(
        float(row.get("close") or 0) < key_support for row in recent
    )


def _moving_average_slope(rows: list[dict], *, period: int, window: int) -> float:
    if len(rows) < period + window:
        return 0.0
    current = sum(float(row.get("close") or 0) for row in rows[-period:]) / period
    previous_end = len(rows) - window
    previous_rows = rows[previous_end - period:previous_end]
    previous = sum(float(row.get("close") or 0) for row in previous_rows) / period
    return current / previous - 1 if previous > 0 else 0.0


def _max_true_run(flags: list[bool]) -> int:
    maximum = current = 0
    for flag in flags:
        current = current + 1 if flag else 0
        maximum = max(maximum, current)
    return maximum
