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
    ma20 = _ma(data, 20)
    ma60 = _ma(data, 60)
    ma120 = _ma(data, 120)
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
    range_5 = (high5 - low5) / close if close > 0 else 0.0
    range_10 = _range(data, 10, close)
    range_20 = _range(data, 20, close)
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
    atr5 = _atr(data, 5)
    atr20 = _atr(data, 20)
    atr14 = _atr(data, 14)
    support_levels = _compute_support_levels(
        data=data,
        current_close=close,
        ma20=ma20,
        ma60=ma60,
        v20=v20,
        atr14=atr14,
        config=config,
    )
    support_price = support_levels["key_support"] or support_price
    support_test_count = _count_support_tests(data, support_price, support_days, support_test_tolerance)
    support_valid = support_levels["support_status"] in {"VALID", "TESTING"}

    return Strategy3Indicators(
        ma5=_ma(data, 5),
        ma10=_ma(data, 10),
        ma20=ma20,
        ma60=ma60,
        ma120=ma120,
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
        range_5=range_5,
        range_10=range_10,
        range_20=range_20,
        range_compression_ok=0 < range_5 < range_10 < range_20,
        close_range_5=(max(close_values) - min(close_values)) / close if close > 0 else 0.0,
        volume_ratio_5_20=v5 / v20 if v20 > 0 else 0.0,
        v3=v3,
        v5=v5,
        v10=v10,
        v20=v20,
        down_day_volume_ratio=down_day_avg_volume / v20 if v20 > 0 else 0.0,
        return_5=_return(data, 5),
        max_up_5=_max_daily_return(data, 5),
        max_down_5=_min_daily_return(data, 5),
        direction_efficiency_5=_direction_efficiency(data, 5),
        avg_close_position_5=_avg_close_position(data, 5),
        min_close_5=min_close_5,
        min_close_10=min_close_10,
        previous_min_close_5=previous_min_close_5,
        no_new_low=no_new_low,
        support_price_10=support_price,
        support_test_count=support_test_count,
        support_valid=support_valid,
        short_support=support_levels["short_support"],
        short_support_zone_low=support_levels["short_support_zone_low"],
        short_support_zone_high=support_levels["short_support_zone_high"],
        key_support=support_levels["key_support"],
        key_support_zone_low=support_levels["key_support_zone_low"],
        key_support_zone_high=support_levels["key_support_zone_high"],
        strong_support=support_levels["strong_support"],
        strong_support_zone_low=support_levels["strong_support_zone_low"],
        strong_support_zone_high=support_levels["strong_support_zone_high"],
        support_status=support_levels["support_status"],
        break_status=support_levels["break_status"],
        nearest_support_distance=support_levels["nearest_support_distance"],
        support_sources=support_levels["support_sources"],
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


def _range(data: list[dict], days: int, close: float) -> float:
    if close <= 0 or len(data) < days:
        return 0.0
    window = data[-days:]
    high = max(float(row["high"]) for row in window)
    low = min(float(row["low"]) for row in window)
    return (high - low) / close


def _daily_returns(data: list[dict], days: int) -> list[float]:
    if len(data) <= days:
        return []
    window = data[-days - 1:]
    values: list[float] = []
    for prev, curr in zip(window[:-1], window[1:]):
        prev_close = float(prev["close"])
        if prev_close <= 0:
            continue
        values.append(float(curr["close"]) / prev_close - 1)
    return values


def _max_daily_return(data: list[dict], days: int) -> float:
    values = _daily_returns(data, days)
    return max(values, default=0.0)


def _min_daily_return(data: list[dict], days: int) -> float:
    values = _daily_returns(data, days)
    return min(values, default=0.0)


def _direction_efficiency(data: list[dict], days: int) -> float:
    if len(data) <= days:
        return 0.0
    base = float(data[-days - 1]["close"])
    if base <= 0:
        return 0.0
    net_change = abs(float(data[-1]["close"]) / base - 1)
    total_move = sum(abs(value) for value in _daily_returns(data, days))
    if total_move <= 0:
        return 0.0
    return net_change / total_move


def _avg_close_position(data: list[dict], days: int) -> float:
    if not data:
        return 0.0
    positions: list[float] = []
    for row in data[-days:]:
        high = float(row["high"])
        low = float(row["low"])
        close = float(row["close"])
        if high <= low:
            positions.append(0.5)
        else:
            positions.append((close - low) / (high - low))
    return _avg_values(positions)


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


def _compute_support_levels(
    *,
    data: list[dict],
    current_close: float,
    ma20: float,
    ma60: float,
    v20: float,
    atr14: float,
    config: dict,
) -> dict:
    validation_days = min(5, max(1, len(data) - 1))
    short_window = _history_window_before_recent(data, 5, 1)
    key_days = int(config.get("dry_support_lookback_days", 10))
    key_window = _history_window_before_recent(data, key_days, validation_days)
    strong_days = int(config.get("support_lookback_days", 20))
    strong_window = _history_window_before_recent(data, strong_days, validation_days)

    short = _build_support_from_base(
        "min_close_5",
        _min_field(short_window, "close"),
        [
            ("low_5", _min_field(short_window, "low")),
            ("ma20", ma20),
        ],
        current_close,
        atr14,
        config,
    )
    key = _build_support_from_base(
        "min_close_10",
        _min_field(key_window, "close"),
        [
            ("low_10", _min_field(key_window, "low")),
            ("platform_low_10", _platform_low(key_window, float(config.get("platform_range_threshold", 0.08)))),
            ("ma20", ma20),
            ("ma60", ma60),
        ],
        current_close,
        atr14,
        config,
    )
    strong = _build_support_from_base(
        "min_close_20",
        _min_field(strong_window, "close"),
        [
            ("low_20", _min_field(strong_window, "low")),
            ("ma60", ma60),
        ],
        current_close,
        atr14,
        config,
    )
    support_status, break_status = _support_break_status(
        data[-max(validation_days, int(config.get("support_effective_break_days", 2))):],
        key["zone_low"],
        key["zone_high"],
        v20,
        int(config.get("support_effective_break_days", 2)),
        float(config.get("support_big_down_return", -0.04)),
        float(config.get("support_big_down_volume_ratio", 1.30)),
    )
    distance = (
        (current_close - key["price"]) / current_close
        if current_close > 0 and key["price"] > 0 else 0.0
    )
    return {
        "short_support": short["price"],
        "short_support_zone_low": short["zone_low"],
        "short_support_zone_high": short["zone_high"],
        "key_support": key["price"],
        "key_support_zone_low": key["zone_low"],
        "key_support_zone_high": key["zone_high"],
        "strong_support": strong["price"],
        "strong_support_zone_low": strong["zone_low"],
        "strong_support_zone_high": strong["zone_high"],
        "support_status": support_status,
        "break_status": break_status,
        "nearest_support_distance": max(0.0, distance),
        "support_sources": key["sources"],
    }


def _history_window_before_recent(data: list[dict], days: int, recent_days: int) -> list[dict]:
    end = max(1, len(data) - recent_days)
    start = max(0, end - days)
    window = data[start:end]
    if window:
        return window
    return data[: max(1, len(data) - 1)]


def _build_support_from_base(
    base_source: str,
    base_price: float,
    related: list[tuple[str, float]],
    current_close: float,
    atr14: float,
    config: dict,
) -> dict:
    price = float(base_price or 0.0)
    if price <= 0:
        price = current_close
    radius = _support_zone_radius(price, atr14, config)
    sources = [base_source]
    merge_tolerance = max(radius, price * 0.02)
    for source, value in related:
        value = float(value or 0.0)
        if value <= 0:
            continue
        if abs(value - price) <= merge_tolerance:
            sources.append(source)
    return {
        "price": price,
        "zone_low": max(0.0, price - radius),
        "zone_high": price + radius,
        "sources": sources,
    }


def _support_zone_radius(price: float, atr14: float, config: dict) -> float:
    pct_radius = price * float(config.get("support_zone_pct", 0.01))
    atr_radius = atr14 * float(config.get("support_zone_atr_ratio", 0.30))
    return max(pct_radius, atr_radius)


def _support_break_status(
    recent: list[dict],
    zone_low: float,
    zone_high: float,
    v20: float,
    break_days: int,
    big_down_return: float,
    big_down_volume_ratio: float,
) -> tuple[str, str]:
    if zone_low <= 0 or not recent:
        return "UNKNOWN", "UNKNOWN"
    closes_below: list[bool] = []
    streak = 0
    effective_break = False
    previous_close = None
    for row in recent:
        close = float(row["close"])
        below = close < zone_low
        closes_below.append(below)
        streak = streak + 1 if below else 0
        if streak >= break_days:
            effective_break = True
        if below and v20 > 0 and float(row["volume"]) >= v20 * big_down_volume_ratio:
            effective_break = True
        if previous_close and previous_close > 0:
            day_return = close / previous_close - 1
            if below and day_return <= big_down_return:
                effective_break = True
        previous_close = close

    current_close = float(recent[-1]["close"])
    if effective_break:
        return "FAILED", "EFFECTIVE_BREAK"
    if current_close < zone_low:
        return "BROKEN", "CLOSE_BELOW_ZONE"
    if any(closes_below[:-1]):
        return "WEAKENING", "RECENT_CLOSE_BELOW_ZONE"
    if current_close <= zone_high:
        return "TESTING", "NOT_BROKEN"
    return "VALID", "NOT_BROKEN"


def _min_field(data: list[dict], field: str) -> float:
    if not data:
        return 0.0
    return min(float(row[field]) for row in data)


def _platform_low(data: list[dict], range_threshold: float) -> float:
    if not data:
        return 0.0
    high = max(float(row["high"]) for row in data)
    low = min(float(row["low"]) for row in data)
    close = float(data[-1]["close"])
    if close <= 0:
        return 0.0
    return low if (high - low) / close <= range_threshold else 0.0


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
