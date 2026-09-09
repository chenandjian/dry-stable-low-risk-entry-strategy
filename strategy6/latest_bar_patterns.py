"""Display-only pattern diagnostics for the latest completed trading bar."""
from __future__ import annotations

import math

from strategy6.indicators import _atr
from strategy6.models import Strategy6LatestBarPattern


def evaluate_latest_bar_patterns(
    rows: list[dict],
    existing: list[Strategy6LatestBarPattern] | None = None,
) -> list[Strategy6LatestBarPattern]:
    """Append latest-bar shapes without changing selection or scoring."""
    patterns = list(existing or [])
    patterns.append(_evaluate_hammer(rows))
    patterns.append(_evaluate_inverted_hammer(rows))
    return patterns


def _evaluate_hammer(rows: list[dict]) -> Strategy6LatestBarPattern:
    pattern = Strategy6LatestBarPattern(code="HAMMER", name="锤子线")
    if len(rows) < 15:
        pattern.risks.append("HAMMER_ATR14_DATA_INSUFFICIENT")
        return pattern

    latest = rows[-1]
    previous_close = _number(rows[-2].get("close"))
    open_ = _number(latest.get("open"))
    high = _number(latest.get("high"))
    low = _number(latest.get("low"))
    close = _number(latest.get("close"))
    pattern.evaluation_date = str(latest.get("date") or "")
    if None in {previous_close, open_, high, low, close}:
        pattern.risks.append("HAMMER_OHLC_INVALID")
        return pattern
    if previous_close <= 0 or low <= 0 or low > min(open_, close) or high < max(open_, close):
        pattern.risks.append("HAMMER_OHLC_INVALID")
        return pattern

    body_bottom = min(open_, close)
    body_top = max(open_, close)
    bar_range = high - low
    body = body_top - body_bottom
    lower_shadow = body_bottom - low
    upper_shadow = high - body_top
    atr14 = _atr(rows, 14)
    pattern.body_bottom = body_bottom
    pattern.body_top = body_top
    pattern.body_direction = "BULLISH" if close > open_ else "BEARISH" if close < open_ else "FLAT"
    if bar_range <= 0 or body <= 0 or atr14 <= 0:
        pattern.risks.append("HAMMER_ZERO_RANGE_OR_BODY")
        return pattern

    body_ratio = body / bar_range
    lower_to_body = lower_shadow / body
    upper_to_body = upper_shadow / body
    range_to_previous_close = bar_range / previous_close
    range_to_atr14 = bar_range / atr14
    pattern.metrics = {
        "bar_range": round(bar_range, 6),
        "atr14": round(atr14, 6),
        "body_ratio": round(body_ratio, 6),
        "lower_shadow_to_body": round(lower_to_body, 6),
        "upper_shadow_to_body": round(upper_to_body, 6),
        "range_to_previous_close": round(range_to_previous_close, 6),
        "range_to_atr14": round(range_to_atr14, 6),
    }

    tolerance = 1e-9
    if body_ratio < 0.10 - tolerance:
        pattern.risks.append("HAMMER_BODY_RATIO_LT_10PCT")
    if body_ratio > 0.25 + tolerance:
        pattern.risks.append("HAMMER_BODY_RATIO_GT_25PCT")
    if lower_to_body < 2.0 - tolerance:
        pattern.risks.append("HAMMER_LOWER_SHADOW_LT_BODY_2")
    if upper_to_body > 0.10 + tolerance:
        pattern.risks.append("HAMMER_UPPER_SHADOW_GT_BODY_0_1")
    if range_to_previous_close < 0.008 - tolerance:
        pattern.risks.append("HAMMER_RANGE_LT_PREVIOUS_CLOSE_0_8PCT")
    if range_to_atr14 < 0.50 - tolerance:
        pattern.risks.append("HAMMER_RANGE_LT_ATR14_0_5")
    if pattern.risks:
        return pattern

    pattern.matched = True
    pattern.status = "DETECTED"
    if pattern.body_direction == "BULLISH":
        pattern.name = "阳线锤子线"
        pattern.signal_type = "BULLISH_HAMMER"
    else:
        pattern.name = "阴线锤子线"
        pattern.signal_type = "BEARISH_HAMMER"
        pattern.risks.append("BEARISH_HAMMER_REQUIRES_CONFIRMATION")
    pattern.reasons.append("LATEST_BAR_EFFECTIVE_HAMMER")
    return pattern


def _evaluate_inverted_hammer(rows: list[dict]) -> Strategy6LatestBarPattern:
    pattern = Strategy6LatestBarPattern(code="INVERTED_HAMMER", name="倒锤子线")
    if len(rows) < 15:
        pattern.risks.append("INVERTED_HAMMER_ATR14_DATA_INSUFFICIENT")
        return pattern

    latest = rows[-1]
    previous_close = _number(rows[-2].get("close"))
    open_ = _number(latest.get("open"))
    high = _number(latest.get("high"))
    low = _number(latest.get("low"))
    close = _number(latest.get("close"))
    pattern.evaluation_date = str(latest.get("date") or "")
    if None in {previous_close, open_, high, low, close}:
        pattern.risks.append("INVERTED_HAMMER_OHLC_INVALID")
        return pattern
    if previous_close <= 0 or low <= 0 or low > min(open_, close) or high < max(open_, close):
        pattern.risks.append("INVERTED_HAMMER_OHLC_INVALID")
        return pattern

    body_bottom = min(open_, close)
    body_top = max(open_, close)
    bar_range = high - low
    body = body_top - body_bottom
    lower_shadow = body_bottom - low
    upper_shadow = high - body_top
    atr14 = _atr(rows, 14)
    pattern.body_bottom = body_bottom
    pattern.body_top = body_top
    pattern.body_direction = "BULLISH" if close > open_ else "BEARISH" if close < open_ else "FLAT"
    if bar_range <= 0 or body <= 0 or atr14 <= 0:
        pattern.risks.append("INVERTED_HAMMER_ZERO_RANGE_OR_BODY")
        return pattern

    context_closes = [_number(row.get("close")) for row in rows[-6:-1]]
    if len(context_closes) != 5 or any(value is None or value <= 0 for value in context_closes):
        pattern.risks.append("INVERTED_HAMMER_CONTEXT_DATA_INSUFFICIENT")
        return pattern

    body_ratio = body / bar_range
    lower_to_body = lower_shadow / body
    upper_to_body = upper_shadow / body
    range_to_previous_close = bar_range / previous_close
    range_to_atr14 = bar_range / atr14
    context_return_5 = context_closes[-1] / context_closes[0] - 1
    context_ma5 = sum(context_closes) / 5
    pattern.metrics = {
        "bar_range": round(bar_range, 6),
        "atr14": round(atr14, 6),
        "body_ratio": round(body_ratio, 6),
        "lower_shadow_to_body": round(lower_to_body, 6),
        "upper_shadow_to_body": round(upper_to_body, 6),
        "range_to_previous_close": round(range_to_previous_close, 6),
        "range_to_atr14": round(range_to_atr14, 6),
        "context_return_5": round(context_return_5, 6),
        "context_ma5": round(context_ma5, 6),
    }

    tolerance = 1e-9
    if body_ratio < 0.10 - tolerance:
        pattern.risks.append("INVERTED_HAMMER_BODY_RATIO_LT_10PCT")
    if body_ratio > 0.25 + tolerance:
        pattern.risks.append("INVERTED_HAMMER_BODY_RATIO_GT_25PCT")
    if upper_to_body < 2.0 - tolerance:
        pattern.risks.append("INVERTED_HAMMER_UPPER_SHADOW_LT_BODY_2")
    if lower_to_body > 0.10 + tolerance:
        pattern.risks.append("INVERTED_HAMMER_LOWER_SHADOW_GT_BODY_0_1")
    if range_to_previous_close < 0.008 - tolerance:
        pattern.risks.append("INVERTED_HAMMER_RANGE_LT_PREVIOUS_CLOSE_0_8PCT")
    if range_to_atr14 < 0.50 - tolerance:
        pattern.risks.append("INVERTED_HAMMER_RANGE_LT_ATR14_0_5")
    if pattern.risks:
        return pattern

    pattern.matched = True
    pattern.status = "DETECTED"
    if context_return_5 < 0 or close < context_ma5:
        pattern.name = "阳线倒锤子线" if close > open_ else "阴线倒锤子线"
        pattern.signal_type = "BULLISH_INVERTED_HAMMER" if close > open_ else "BEARISH_INVERTED_HAMMER"
        pattern.reasons.append("LATEST_BAR_EFFECTIVE_INVERTED_HAMMER")
        pattern.risks.append("INVERTED_HAMMER_REQUIRES_CONFIRMATION")
    elif context_return_5 > 0.02 and close >= context_ma5:
        pattern.name = "射击之星风险"
        pattern.signal_type = "SHOOTING_STAR"
        pattern.risks.append("SHOOTING_STAR_AFTER_RISE")
    else:
        pattern.name = "上影锤形K线（位置不明确）"
        pattern.signal_type = "UPPER_SHADOW_HAMMER_UNCLEAR"
        pattern.risks.append("INVERTED_HAMMER_CONTEXT_UNCLEAR")
    return pattern


def _number(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None
