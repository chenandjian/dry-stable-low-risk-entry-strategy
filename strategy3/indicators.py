"""策略3指标计算。"""
from __future__ import annotations

from strategy3.models import Strategy3Indicators


def compute_indicators(
    data: list[dict],
    config: dict,
    market_data: list[dict] | None = None,
) -> Strategy3Indicators:
    close = float(data[-1]["close"])
    pullback_lookback_days = int(config.get("pullback_lookback_days", 60))
    recent_high = _max(data[-pullback_lookback_days:], "high")
    high_120 = _max(data[-120:], "high")
    return_60 = _return(data, 60)
    index_return_60 = _return(market_data, 60) if market_data else 0.0
    ma60 = _ma(data, 60)
    ma60_20_days_ago = _ma(data[:-20], 60) if len(data) >= 80 else 0.0

    v3 = _avg(data[-3:], "volume")
    v5 = _avg(data[-5:], "volume")
    v10 = _avg(data[-10:], "volume")
    v20 = _avg(data[-20:], "volume")
    down_days = [row for row in data[-20:] if float(row["close"]) < float(row["open"])]
    down_day_avg_volume = _avg(down_days, "volume") if down_days else 0.0

    last5 = data[-5:]
    close_values = [float(row["close"]) for row in last5]
    high5 = max(float(row["high"]) for row in last5)
    low5 = min(float(row["low"]) for row in last5)
    last10 = data[-10:] if len(data) >= 10 else data
    min_close_5 = min(close_values)
    min_close_10 = min(float(row["close"]) for row in last10)
    previous5 = data[-10:-5] if len(data) >= 10 else []
    previous_min_close_5 = min((float(row["close"]) for row in previous5), default=min_close_5)
    no_new_low_tolerance = float(config.get("dry_no_new_low_tolerance", 0.995))
    no_new_low = (
        previous_min_close_5 <= 0
        or min_close_5 >= previous_min_close_5 * no_new_low_tolerance
    )
    support_days = int(config.get("dry_support_lookback_days", 10))
    support_history = data[-support_days - 5:-5] if len(data) > support_days + 5 else data[:-5]
    support_price = min((float(row["close"]) for row in support_history), default=0.0)
    support_test_tolerance = float(config.get("dry_support_test_tolerance", 0.02))
    support_break_tolerance = float(config.get("dry_support_break_tolerance", 0.98))
    support_test_count = _count_support_tests(data, support_price, support_days, support_test_tolerance)
    support_valid = _support_valid(data, support_price, support_days, support_break_tolerance)
    atr5 = _atr(data, 5)
    atr20 = _atr(data, 20)

    return Strategy3Indicators(
        ma5=_ma(data, 5),
        ma10=_ma(data, 10),
        ma20=_ma(data, 20),
        ma60=ma60,
        ma120=_ma(data, 120),
        return_3=_return(data, 3),
        return_20=_return(data, 20),
        return_60=return_60,
        return_120=_return(data, 120),
        high_120=high_120,
        drawdown_from_high_120=(high_120 - close) / high_120 if high_120 > 0 else 0.0,
        relative_strength_60=return_60 - index_return_60,
        ma60_slope_20=(ma60 / ma60_20_days_ago - 1) if ma60_20_days_ago > 0 else 0.0,
        recent_high=recent_high,
        pullback_pct=(recent_high - close) / recent_high if recent_high > 0 else 0.0,
        range_5=(high5 - low5) / close if close > 0 else 0.0,
        close_range_5=(max(close_values) - min(close_values)) / close if close > 0 else 0.0,
        volume_ratio_5_20=v5 / v20 if v20 > 0 else 0.0,
        v3=v3,
        v5=v5,
        v10=v10,
        v20=v20,
        down_day_volume_ratio=down_day_avg_volume / v20 if v20 > 0 else 0.0,
        return_5=_return(data, 5),
        min_close_5=min_close_5,
        min_close_10=min_close_10,
        previous_min_close_5=previous_min_close_5,
        no_new_low=no_new_low,
        support_price_10=support_price,
        support_test_count=support_test_count,
        support_valid=support_valid,
        bear_body_shrink=_bear_body_shrink(data),
        lower_shadow_count=_lower_shadow_count(
            data,
            5,
            float(config.get("dry_lower_shadow_threshold", 0.40)),
        ),
        down_volume_ratio_5=_down_volume_ratio(data, 5),
        atr_ratio_5_20=atr5 / atr20 if atr20 > 0 else 0.0,
        has_big_down_volume=_has_big_down_volume(
            data,
            v20,
            float(config.get("dry_big_down_return", -0.04)),
            float(config.get("dry_big_down_volume_ratio", 1.30)),
        ),
        current_close=close,
    )


def _ma(data: list[dict], days: int) -> float:
    if len(data) < days:
        return 0.0
    return _avg(data[-days:], "close")


def _avg(data: list[dict], field: str) -> float:
    if not data:
        return 0.0
    return sum(float(row[field]) for row in data) / len(data)


def _max(data: list[dict], field: str) -> float:
    if not data:
        return 0.0
    return max(float(row[field]) for row in data)


def _return(data: list[dict] | None, days: int) -> float:
    if not data or len(data) <= days:
        return 0.0
    base = float(data[-days - 1]["close"])
    if base <= 0:
        return 0.0
    return float(data[-1]["close"]) / base - 1


def _count_support_tests(data: list[dict], support: float, days: int, tolerance: float) -> int:
    if support <= 0:
        return 0
    threshold = support * (1 + tolerance)
    return sum(1 for row in data[-days:] if float(row["low"]) <= threshold)


def _support_valid(data: list[dict], support: float, days: int, break_tolerance: float) -> bool:
    if support <= 0:
        return False
    floor = support * break_tolerance
    return all(float(row["close"]) >= floor for row in data[-days:])


def _bear_body_shrink(data: list[dict]) -> bool:
    prior = [_bear_body_ratio(row) for row in data[-10:-5] if _is_bear(row)]
    recent = [_bear_body_ratio(row) for row in data[-5:] if _is_bear(row)]
    if not recent:
        return True
    if not prior:
        return False
    return _avg_values(recent[-3:]) < _avg_values(prior)


def _lower_shadow_count(data: list[dict], days: int, threshold: float) -> int:
    count = 0
    for row in data[-days:]:
        open_ = float(row["open"])
        high = float(row["high"])
        low = float(row["low"])
        close = float(row["close"])
        full_range = high - low
        if full_range <= 0:
            continue
        lower_shadow = min(open_, close) - low
        if lower_shadow / full_range >= threshold:
            count += 1
    return count


def _down_volume_ratio(data: list[dict], days: int) -> float:
    window = data[-days:]
    total_volume = sum(float(row["volume"]) for row in window)
    if total_volume <= 0:
        return 0.0
    down_volume = sum(float(row["volume"]) for row in window if _is_bear(row))
    return down_volume / total_volume


def _has_big_down_volume(data: list[dict], v20: float, drop_threshold: float, volume_ratio: float) -> bool:
    if v20 <= 0 or len(data) < 2:
        return False
    for prev, curr in zip(data[-6:-1], data[-5:]):
        prev_close = float(prev["close"])
        if prev_close <= 0:
            continue
        change = float(curr["close"]) / prev_close - 1
        if change <= drop_threshold and float(curr["volume"]) >= v20 * volume_ratio:
            return True
    return False


def _atr(data: list[dict], days: int) -> float:
    if not data:
        return 0.0
    start = max(0, len(data) - days)
    values: list[float] = []
    for idx in range(start, len(data)):
        row = data[idx]
        high = float(row["high"])
        low = float(row["low"])
        prev_close = float(data[idx - 1]["close"]) if idx > 0 else float(row["close"])
        values.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    return _avg_values(values)


def _is_bear(row: dict) -> bool:
    return float(row["close"]) < float(row["open"])


def _bear_body_ratio(row: dict) -> float:
    open_ = float(row["open"])
    close = float(row["close"])
    return (open_ - close) / open_ if open_ > 0 else 0.0


def _avg_values(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)
