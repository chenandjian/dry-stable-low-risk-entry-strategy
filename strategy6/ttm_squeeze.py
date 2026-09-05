"""TTM Squeeze quality diagnostics for Strategy6."""
from __future__ import annotations

from math import isfinite, sqrt

from strategy6.models import Strategy6TtmSqueeze


def _population_stddev(values: list[float]) -> float:
    if not values:
        raise ValueError("population standard deviation requires values")
    mean = sum(values) / len(values)
    return sqrt(sum((value - mean) ** 2 for value in values) / len(values))


def _sma_series(values: list[float], period: int) -> list[float | None]:
    result: list[float | None] = [None] * len(values)
    if period <= 0 or len(values) < period:
        return result
    rolling_sum = sum(values[:period])
    result[period - 1] = rolling_sum / period
    for index in range(period, len(values)):
        rolling_sum += values[index] - values[index - period]
        result[index] = rolling_sum / period
    return result


def _ema_series(values: list[float], period: int) -> list[float | None]:
    result: list[float | None] = [None] * len(values)
    if period <= 0 or len(values) < period:
        return result
    previous = sum(values[:period]) / period
    result[period - 1] = previous
    alpha = 2.0 / (period + 1.0)
    for index in range(period, len(values)):
        previous = alpha * values[index] + (1.0 - alpha) * previous
        result[index] = previous
    return result


def _true_range_series(rows: list[dict]) -> list[float]:
    result: list[float] = []
    previous_close: float | None = None
    for row in rows:
        high = float(row["high"])
        low = float(row["low"])
        if previous_close is None:
            true_range = high - low
        else:
            true_range = max(
                high - low,
                abs(high - previous_close),
                abs(low - previous_close),
            )
        result.append(true_range)
        previous_close = float(row["close"])
    return result


def _wilder_atr_series(rows: list[dict], period: int) -> list[float | None]:
    true_ranges = _true_range_series(rows)
    result: list[float | None] = [None] * len(rows)
    if period <= 0 or len(rows) < period:
        return result
    previous = sum(true_ranges[:period]) / period
    result[period - 1] = previous
    for index in range(period, len(rows)):
        previous = ((period - 1) * previous + true_ranges[index]) / period
        result[index] = previous
    return result


def _linear_regression_last(values: list[float]) -> float:
    if not values:
        raise ValueError("linear regression requires values")
    count = len(values)
    x_mean = (count - 1) / 2.0
    y_mean = sum(values) / count
    denominator = sum((x - x_mean) ** 2 for x in range(count))
    if denominator == 0:
        return values[-1]
    slope = sum(
        (x - x_mean) * (value - y_mean)
        for x, value in enumerate(values)
    ) / denominator
    intercept = y_mean - slope * x_mean
    return intercept + slope * (count - 1)


def _momentum_direction(momentum: float | None, previous: float | None, close: float) -> str:
    if momentum is None or previous is None:
        return "UNKNOWN"
    tolerance = max(abs(previous), abs(close) * 0.0001, 1e-9) * 0.001
    difference = momentum - previous
    if abs(difference) <= tolerance:
        return "FLAT"
    return "RISING" if difference > 0 else "FALLING"


def _bands_inside_keltner(
    bb_upper: float,
    bb_lower: float,
    kc_upper: float,
    kc_lower: float,
) -> bool:
    return bb_upper < kc_upper and bb_lower > kc_lower


def classify_ttm_state(
    *,
    enabled: bool,
    calculable: bool,
    squeeze_on: bool,
    previous_squeeze_on: bool,
    squeeze_days: int,
    momentum: float | None,
    previous_momentum: float | None,
    close: float,
    min_bullish_days: int,
) -> Strategy6TtmSqueeze:
    if not enabled:
        return Strategy6TtmSqueeze(status="DISABLED")
    if not calculable or momentum is None or previous_momentum is None:
        return Strategy6TtmSqueeze(
            status="INSUFFICIENT_DATA",
            risk_tags=["TTM_DATA_INSUFFICIENT"],
        )

    direction = _momentum_direction(momentum, previous_momentum, close)
    fired = not squeeze_on and previous_squeeze_on
    reasons: list[str] = []
    risk_tags: list[str] = []
    if squeeze_on:
        reasons.append("TTM_SQUEEZE_ON")
        if squeeze_days >= 3:
            reasons.append("TTM_SQUEEZE_3D_PLUS")
    if fired:
        reasons.append("TTM_FIRED")
    if momentum > 0:
        reasons.append("TTM_MOMENTUM_POSITIVE")
    if direction == "RISING":
        reasons.append("TTM_MOMENTUM_RISING")

    bullish_momentum = momentum > 0 and direction == "RISING"
    if fired:
        if bullish_momentum:
            status, score = "FIRED_BULLISH", 4
        else:
            status, score = "FIRED_WEAK", 0
            risk_tags.append("TTM_FIRED_WITHOUT_BULLISH_MOMENTUM")
    elif squeeze_on:
        if momentum <= 0 and direction == "FALLING":
            status, score = "SQUEEZE_BEARISH", 0
            risk_tags.append("TTM_SQUEEZE_BEARISH_MOMENTUM")
        elif squeeze_days >= min_bullish_days and bullish_momentum:
            status, score = "SQUEEZE_BULLISH", 3
        else:
            status, score = "SQUEEZE_NEUTRAL", 2
    else:
        status, score = "OFF", 0

    return Strategy6TtmSqueeze(
        status=status,
        squeeze_on=squeeze_on,
        squeeze_days=squeeze_days,
        fired=fired,
        momentum=momentum,
        previous_momentum=previous_momentum,
        momentum_direction=direction,
        score=score,
        reasons=reasons,
        risk_tags=risk_tags,
    )


def _valid_ohlc_rows(rows: list[dict]) -> bool:
    for row in rows:
        try:
            open_price = float(row["open"])
            high = float(row["high"])
            low = float(row["low"])
            close = float(row["close"])
        except (KeyError, TypeError, ValueError):
            return False
        if not all(isfinite(value) and value > 0 for value in (open_price, high, low, close)):
            return False
        if high < max(open_price, close) or low > min(open_price, close) or high < low:
            return False
    return True


def calculate_ttm_squeeze(rows: list[dict], config: dict) -> Strategy6TtmSqueeze:
    enabled = bool(config.get("enabled", True))
    if not enabled:
        return Strategy6TtmSqueeze(status="DISABLED")

    bb_period = int(config.get("bb_period", 20))
    bb_stddev = float(config.get("bb_stddev", 2.0))
    kc_ema_period = int(config.get("kc_ema_period", 20))
    kc_atr_period = int(config.get("kc_atr_period", 20))
    kc_atr_multiplier = float(config.get("kc_atr_multiplier", 1.5))
    momentum_period = int(config.get("momentum_period", 20))
    min_bullish_days = int(config.get("bullish_squeeze_min_days", 3))
    minimum_rows = max(
        bb_period + 1,
        kc_ema_period + 1,
        kc_atr_period + 1,
        momentum_period * 2,
    )
    if len(rows) < minimum_rows or not _valid_ohlc_rows(rows):
        return Strategy6TtmSqueeze(
            status="INSUFFICIENT_DATA",
            risk_tags=["TTM_DATA_INSUFFICIENT"],
        )

    closes = [float(row["close"]) for row in rows]
    highs = [float(row["high"]) for row in rows]
    lows = [float(row["low"]) for row in rows]
    bb_middle = _sma_series(closes, bb_period)
    kc_middle = _ema_series(closes, kc_ema_period)
    atr = _wilder_atr_series(rows, kc_atr_period)

    bb_upper: list[float | None] = [None] * len(rows)
    bb_lower: list[float | None] = [None] * len(rows)
    kc_upper: list[float | None] = [None] * len(rows)
    kc_lower: list[float | None] = [None] * len(rows)
    squeeze_flags: list[bool] = [False] * len(rows)
    for index in range(len(rows)):
        if bb_middle[index] is not None:
            window = closes[index - bb_period + 1:index + 1]
            deviation = _population_stddev(window)
            bb_upper[index] = bb_middle[index] + bb_stddev * deviation
            bb_lower[index] = bb_middle[index] - bb_stddev * deviation
        if kc_middle[index] is not None and atr[index] is not None:
            kc_upper[index] = kc_middle[index] + kc_atr_multiplier * atr[index]
            kc_lower[index] = kc_middle[index] - kc_atr_multiplier * atr[index]
        if None not in (bb_upper[index], bb_lower[index], kc_upper[index], kc_lower[index]):
            squeeze_flags[index] = _bands_inside_keltner(
                float(bb_upper[index]),
                float(bb_lower[index]),
                float(kc_upper[index]),
                float(kc_lower[index]),
            )

    sma_momentum = _sma_series(closes, momentum_period)
    deltas: list[float | None] = [None] * len(rows)
    for index in range(momentum_period - 1, len(rows)):
        window_high = max(highs[index - momentum_period + 1:index + 1])
        window_low = min(lows[index - momentum_period + 1:index + 1])
        donchian_midline = (window_high + window_low) / 2.0
        deltas[index] = closes[index] - (donchian_midline + sma_momentum[index]) / 2.0

    momentum_values: list[float | None] = [None] * len(rows)
    for index in range(momentum_period * 2 - 2, len(rows)):
        window = deltas[index - momentum_period + 1:index + 1]
        if all(value is not None for value in window):
            momentum_values[index] = _linear_regression_last([float(value) for value in window])

    current_index = len(rows) - 1
    previous_index = current_index - 1
    momentum = momentum_values[current_index]
    previous_momentum = momentum_values[previous_index]
    squeeze_on = squeeze_flags[current_index]
    previous_squeeze_on = squeeze_flags[previous_index]
    squeeze_days = 0
    if squeeze_on:
        for flag in reversed(squeeze_flags[:current_index + 1]):
            if not flag:
                break
            squeeze_days += 1

    result = classify_ttm_state(
        enabled=True,
        calculable=momentum is not None and previous_momentum is not None,
        squeeze_on=squeeze_on,
        previous_squeeze_on=previous_squeeze_on,
        squeeze_days=squeeze_days,
        momentum=momentum,
        previous_momentum=previous_momentum,
        close=closes[current_index],
        min_bullish_days=min_bullish_days,
    )
    result.bb_upper = bb_upper[current_index]
    result.bb_lower = bb_lower[current_index]
    result.kc_upper = kc_upper[current_index]
    result.kc_lower = kc_lower[current_index]
    return result
